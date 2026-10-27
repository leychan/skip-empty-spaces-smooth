// SPDX-License-Identifier: MIT
// Direct scene composition: no QQuickWindow, thumbnail texture or screen copy.
#include "effect/effect.h"
#include "effect/effecthandler.h"
#include "effect/effectwindow.h"
#include "core/renderviewport.h"
#include "core/output.h"
#include "scene/scene.h"
#include "virtualdesktops.h"
#include "config-kwin.h"
#include "core.h"
#include <KConfigGroup>
#include <QDBusConnection>
#include <QCoreApplication>
#include <QDateTime>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPointer>
#include <QTimer>
#include <algorithm>
#include <cmath>
#include <chrono>
#include <optional>
#include <vector>

using namespace KWin;

class OccupiedSlide : public Effect
{
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.kde.kwin.OccupiedSpaces")
    Q_PROPERTY(QString renderer READ renderer)
    Q_PROPERTY(QString buildId READ buildId)
    Q_PROPERTY(bool active READ isActive)
    Q_PROPERTY(bool screenLocked READ screenLocked)
    Q_PROPERTY(bool tracking READ tracking)
    Q_PROPERTY(qreal progress READ progress)
    Q_PROPERTY(qulonglong frames READ frames)
    Q_PROPERTY(qreal releaseVelocity READ releaseVelocity)
    Q_PROPERTY(QString traceLog READ traceLog)
public:
    OccupiedSlide()
    {
        reconfigure(ReconfigureAll);
        connect(effects, &EffectsHandler::desktopChanging, this, &OccupiedSlide::changing);
        connect(effects, &EffectsHandler::desktopChanged, this, &OccupiedSlide::changed);
        connect(effects, QOverload<>::of(&EffectsHandler::desktopChangingCancelled), this, [this]() {
            if (m_tracking && !m_preview) settle(0);
        });
        connect(effects, &EffectsHandler::desktopAdded, this, &OccupiedSlide::finish);
        connect(effects, &EffectsHandler::desktopRemoved, this, &OccupiedSlide::finish);
        connect(effects, &EffectsHandler::screenAdded, this, &OccupiedSlide::finish);
        connect(effects, &EffectsHandler::screenRemoved, this, &OccupiedSlide::finish);
        connect(effects, &EffectsHandler::currentActivityAboutToChange, this, [this]() {
            m_activityChanging = true;
            finish();
        });
        connect(effects, &EffectsHandler::currentActivityChanged, this, [this]() { m_activityChanging = false; });
        connect(effects, &EffectsHandler::screenAboutToLock, this, &OccupiedSlide::finish);
        connect(effects, &EffectsHandler::windowAdded, this, [this](EffectWindow *w) { retain(w); });
        connect(effects, &EffectsHandler::windowDeleted, this, [this](EffectWindow *w) { m_windows.remove(w); });
        m_previewTimer.setSingleShot(true);
        connect(&m_previewTimer, &QTimer::timeout, this, &OccupiedSlide::finish);
        m_watchdog.setSingleShot(true);
        m_watchdog.setInterval(4000);
        connect(&m_watchdog, &QTimer::timeout, this, &OccupiedSlide::finish);
        m_registered = QDBusConnection::sessionBus().registerObject(QStringLiteral("/OccupiedSpaces"), this,
            QDBusConnection::ExportScriptableSlots | QDBusConnection::ExportAllProperties);
    }
    ~OccupiedSlide() override
    {
        finish();
        if (m_registered) QDBusConnection::sessionBus().unregisterObject(QStringLiteral("/OccupiedSpaces"));
    }
    QString renderer() const { return QStringLiteral("native-window-scene"); }
    QString buildId() const { return QStringLiteral(SPACES_BUILD); }
    bool isActive() const override { return m_active && !effects->isScreenLocked(); }
    bool screenLocked() const { return effects->isScreenLocked(); }
    bool tracking() const { return m_tracking; }
    qreal progress() const { return m_progress; }
    qulonglong frames() const { return m_frames; }
    qreal releaseVelocity() const { return m_initialVelocity; }
    QString traceLog() const { return QString::fromUtf8(QJsonDocument(m_events).toJson(QJsonDocument::Compact)); }
    int requestedEffectChainPosition() const override { return 50; }

    void reconfigure(ReconfigureFlags) override
    {
        KConfigGroup config(effects->config(), QStringLiteral("Effect-skip-empty-spaces-smooth"));
        KConfigGroup slide(effects->config(), QStringLiteral("Effect-slide"));
        m_gap = config.readEntry("HorizontalGap", slide.readEntry("HorizontalGap", 45));
        m_background = config.readEntry("SlideBackground", slide.readEntry("SlideBackground", true));
        m_factor = std::max(0.0, config.readEntry("AnimationTimeFactor", effects->animationTimeFactor()));
    }

    void prePaintScreen(ScreenPrePaintData &data) override
    {
        if (m_active && m_output && data.screen == m_output) {
            const auto timestamp = data.view->nextPresentationTimestamp();
            if (!m_tracking && !m_preview) {
                if (m_motionTimestamp) {
                    const double elapsed = std::chrono::duration<double>(timestamp - *m_motionTimestamp).count();
                    advance(std::clamp(elapsed, 0.0, .05));
                }
                if (!m_motionTimestamp || timestamp > *m_motionTimestamp) m_motionTimestamp = timestamp;
            }
            data.mask |= PAINT_SCREEN_TRANSFORMED;
            ++m_frames;
        }
        effects->prePaintScreen(data);
    }
    void prePaintWindow(RenderView *view, EffectWindow *w, WindowPrePaintData &data) override
    {
        if (m_active && w->screen() == m_output) data.setTransformed();
        effects->prePaintWindow(view, w, data);
    }
    void paintWindow(const RenderTarget &target, const RenderViewport &viewport, EffectWindow *w,
                     int mask, const Region &region, WindowPaintData &data) override
    {
        if (!m_active || w->screen() != m_output) {
            effects->paintWindow(target, viewport, w, mask, region, data);
            return;
        }
        const bool fixed = w->isDock() || (w->isOnAllDesktops() && !w->isDesktop()) ||
            (w->isDesktop() && !m_background) || w == m_moving;
        if (fixed) {
            effects->paintWindow(target, viewport, w, mask, region, data);
            return;
        }
        if (m_origin == m_destination) {
            if (w->isOnDesktop(m_origin)) effects->paintWindow(target, viewport, w, mask, region, data);
            return;
        }
        const double scale = m_output->scale();
        const double stride = std::round((m_output->geometry().width() + m_gap) * scale) / scale;
        const double offset = std::round(m_progress * stride * scale) / scale;
        const auto draw = [&](double x) {
            const RectF bounds(m_output->geometry());
            const RectF clip = bounds.translated(QPointF(x, 0)).intersected(bounds);
            if (clip.isEmpty()) return;
            WindowPaintData translated(data);
            translated += QPointF(x, 0);
            effects->paintWindow(target, viewport, w, mask,
                region.intersected(viewport.mapToDeviceCoordinatesAligned(clip)), translated);
        };
        if (w->isOnDesktop(m_origin)) draw(-m_step * offset);
        if (w->isOnDesktop(m_destination)) draw(m_step * (stride - offset));
    }
    void postPaintScreen() override
    {
        if (m_finishPending) finish();
        else if (m_active && !m_tracking && !m_preview && m_output) effects->addRepaint(m_output->geometry());
        effects->postPaintScreen();
    }

public Q_SLOTS:
    Q_SCRIPTABLE bool preview(const QString &outputName, double progress)
    {
        if (effects->isScreenLocked() || m_active || (effects->hasActiveFullScreenEffect() && effects->activeFullScreenEffect() != this)) return false;
        for (auto output : effects->screens()) {
            if (output->name() != outputName) continue;
            auto origin = effects->currentDesktop(output);
            prepare(output, origin, nextOccupied(origin, output, 1), 1, nullptr);
            m_preview = true;
            m_tracking = false;
            m_progress = std::clamp(progress, 0.0, 1.0);
            m_previewTimer.start(4000);
            effects->addRepaint(output->geometry());
            record("preview");
            return true;
        }
        return false;
    }
    Q_SCRIPTABLE void endPreview() { if (m_preview) finish(); }
    Q_SCRIPTABLE bool benchmark(const QString &outputName)
    {
        if (!preview(outputName, 0.65)) return false;
        m_preview = false;
        settle(0);
        return true;
    }

private:
    struct WindowState {
        EffectWindowVisibleRef visible;
        QVariant blur;
        QVariant contrast;
        bool elevated = false;
    };
    bool occupied(VirtualDesktop *desktop, LogicalOutput *output) const
    {
        for (auto w : effects->stackingOrder()) {
            if (!w->isDeleted() && !w->isDesktop() && !w->isDock() && !w->isOnAllDesktops() &&
                (w->isNormalWindow() || w->isDialog()) && w->screen() == output &&
                w->isOnDesktop(desktop) && w->isOnActivity(effects->currentActivity())) return true;
        }
        return false;
    }
    VirtualDesktop *nextOccupied(VirtualDesktop *origin, LogicalOutput *output, int step) const
    {
        const auto desktops = effects->desktops();
        const int index = desktops.indexOf(origin);
        const int count = desktops.size();
        if (index < 0 || !count) return origin;
        const int chosen = Spaces::nextOccupied(count, index, step, effects->optionRollOverDesktops(),
            [&](int candidate) { return occupied(desktops[candidate], output); });
        return desktops[chosen];
    }
    VirtualDesktop *adjacent(VirtualDesktop *origin, int step) const
    {
        const auto desktops = effects->desktops();
        const int position = desktops.indexOf(origin) + step;
        if (position < 0 || position >= desktops.size()) {
            if (!effects->optionRollOverDesktops()) return origin;
        }
        return desktops[(position % desktops.size() + desktops.size()) % desktops.size()];
    }
    void retain(EffectWindow *w)
    {
        if (!m_active || m_windows.contains(w)) return;
        const bool onOutput = w->screen() == m_output;
        const bool onPage = onOutput && (w->isOnDesktop(m_origin) || w->isOnDesktop(m_destination));
        WindowState state{onPage ? EffectWindowVisibleRef(w, EffectWindow::PAINT_DISABLED_BY_DESKTOP) : EffectWindowVisibleRef(),
            w->data(WindowForceBlurRole), w->data(WindowForceBackgroundContrastRole), onOutput && w->isDock()};
        m_windows.insert(w, state);
        w->setData(WindowForceBlurRole, true);
        w->setData(WindowForceBackgroundContrastRole, true);
        if (state.elevated) effects->setElevatedWindow(w, true);
    }
    void prepare(LogicalOutput *output, VirtualDesktop *origin, VirtualDesktop *destination, int step, EffectWindow *moving)
    {
        finish();
        m_output = output;
        m_origin = origin;
        m_destination = destination;
        m_native = adjacent(origin, step);
        m_layout = effects->desktops();
        m_activity = effects->currentActivity();
        m_wraps = effects->optionRollOverDesktops();
        m_step = step;
        m_moving = moving;
        m_active = true;
        m_progress = 0;
        m_velocity = 0;
        m_samples.clear();
        m_motionTimestamp.reset();
        m_frames = 0;
        for (auto w : effects->stackingOrder()) retain(w);
        effects->setActiveFullScreenEffect(this);
        record("start");
    }
    void changing(VirtualDesktop *origin, QPointF offset, EffectWindow *moving, LogicalOutput *output)
    {
        if (m_internal || m_activityChanging || effects->desktopGridHeight() != 1 || offset.x() == 0 ||
            (effects->hasActiveFullScreenEffect() && effects->activeFullScreenEffect() != this)) return;
        const int step = offset.x() > 0 ? 1 : -1;
        if (!m_active || !m_tracking || m_output != output || m_origin != origin || m_step != step)
            prepare(output, origin, nextOccupied(origin, output, step), step, moving);
        m_tracking = true;
        m_watchdog.start();
        m_progress = m_origin == m_destination ? 0 : std::min(std::abs(offset.x()), 1.0);
        const double now = steadySeconds();
        m_samples.push_back({now, m_progress});
        while (m_samples.size() > 2 && m_samples.front().time < now - .1) m_samples.erase(m_samples.begin());
        effects->addRepaint(output->geometry());
    }
    void changed(VirtualDesktop *old, VirtualDesktop *current, EffectWindow *moving, LogicalOutput *output)
    {
        if (m_internal || m_activityChanging || effects->desktopGridHeight() != 1 || old == current || !old || !current ||
            (effects->hasActiveFullScreenEffect() && effects->activeFullScreenEffect() != this)) return;
        const bool valid = m_layout == effects->desktops() && m_activity == effects->currentActivity() &&
            m_wraps == effects->optionRollOverDesktops() && effects->desktopGridHeight() == 1;
        if (m_active && m_tracking && valid && m_output == output && (current == m_native || current == m_origin)) {
            auto destination = current == m_origin || !occupied(m_destination, output) ? m_origin.data() : m_destination.data();
            m_internal = true;
            effects->setCurrentDesktop(destination, output);
            m_internal = false;
            settle(destination == m_origin ? 0 : 1);
        } else {
            const auto desktops = effects->desktops();
            prepare(output, old, current, desktops.indexOf(current) >= desktops.indexOf(old) ? 1 : -1, moving);
            settle(1);
        }
    }
    void settle(double target)
    {
        m_previewTimer.stop();
        m_initialVelocity = m_tracking ? Spaces::releaseVelocity(m_samples, steadySeconds(), m_progress, target, m_factor) : 0;
        m_tracking = false;
        m_watchdog.start();
        m_anchor = target;
        m_velocity = m_initialVelocity;
        m_motionTimestamp = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch());
        record("release");
        if (!m_factor || m_origin == m_destination || m_progress == target) { m_progress = target; finish(); return; }
        effects->addRepaint(m_output->geometry());
    }
    void advance(double seconds)
    {
        if (!(seconds > 0)) return;
        Spaces::advance(m_progress, m_velocity, m_anchor, m_factor, seconds);
        const double stride = std::round((m_output->geometry().width() + m_gap) * m_output->scale());
        if (std::round(m_progress * stride) == std::round(m_anchor * stride)) {
            m_progress = m_anchor;
            m_finishPending = true;
        }
    }
    void finish()
    {
        if (!m_active) return;
        m_previewTimer.stop();
        m_watchdog.stop();
        record("finish");
        for (auto it = m_windows.cbegin(); it != m_windows.cend(); ++it) {
            it.key()->setData(WindowForceBlurRole, it->blur);
            it.key()->setData(WindowForceBackgroundContrastRole, it->contrast);
            if (it->elevated) effects->setElevatedWindow(it.key(), false);
        }
        m_windows.clear();
        m_active = false;
        m_tracking = false;
        m_preview = false;
        m_finishPending = false;
        if (effects->activeFullScreenEffect() == this) effects->setActiveFullScreenEffect(nullptr);
        if (m_output) effects->addRepaint(m_output->geometry());
        m_moving = nullptr;
        m_output = nullptr;
        m_origin = nullptr;
        m_destination = nullptr;
        m_native = nullptr;
    }
    void record(const char *event)
    {
        m_events.append(QJsonObject{{"time", QDateTime::currentMSecsSinceEpoch()}, {"event", QString::fromLatin1(event)},
            {"progress", m_progress}, {"releaseVelocity", m_initialVelocity},
            {"output", m_output ? m_output->name() : QString()}});
        while (m_events.size() > 48) m_events.removeFirst();
    }
    QPointer<LogicalOutput> m_output;
    QPointer<VirtualDesktop> m_origin, m_destination, m_native;
    QList<VirtualDesktop *> m_layout;
    QString m_activity;
    EffectWindow *m_moving = nullptr;
    QHash<EffectWindow *, WindowState> m_windows;
    static double steadySeconds() {
        return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    std::vector<Spaces::GestureSample> m_samples;
    std::optional<std::chrono::nanoseconds> m_motionTimestamp;
    QTimer m_previewTimer;
    QTimer m_watchdog;
    QJsonArray m_events;
    double m_progress = 0, m_anchor = 0, m_velocity = 0, m_factor = 1;
    double m_initialVelocity = 0;
    int m_gap = 45, m_step = 1;
    qulonglong m_frames = 0;
    bool m_active = false, m_tracking = false, m_preview = false, m_internal = false;
    bool m_finishPending = false, m_background = true, m_registered = false;
    bool m_wraps = false;
    bool m_activityChanging = false;
};

KWIN_EFFECT_FACTORY_SUPPORTED_ENABLED(OccupiedSlide, "metadata.json",
    return QCoreApplication::applicationVersion() == KWIN_VERSION_STRING && effects->animationsSupported();, return false;)
#include "renderer.moc"
