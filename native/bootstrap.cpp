// SPDX-License-Identifier: MIT
#include "effect/effecthandler.h"
#include <QCoreApplication>
#include <QQmlEngine>
#include <QQmlExtensionPlugin>
#include <QTimer>
#include <QUrl>

namespace {
quint64 generation = 0;
QHash<QString, quint64> owners;
}

class Bootstrap : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool loaded READ loaded NOTIFY loadedChanged)
    Q_PROPERTY(QString effectId READ effectId CONSTANT)
public:
    using QObject::QObject;
    ~Bootstrap() override
    {
        if (!m_loaded || !KWin::effects) return;
        const auto id = effectId();
        const auto owner = m_owner;
        const auto path = m_path;
        QTimer::singleShot(0, KWin::effects, [id, owner, path]() {
            if (owners.value(id) == owner) {
                KWin::effects->unloadEffect(id);
                owners.remove(id);
                QCoreApplication::removeLibraryPath(path);
            }
        });
    }
    bool loaded() const { return m_loaded; }
    QString effectId() const { return QStringLiteral(SPACES_ID); }
    Q_INVOKABLE bool load(const QUrl &url)
    {
        if (m_loaded) return true;
        m_path = url.toLocalFile();
        if (m_path.isEmpty()) return false;
        QCoreApplication::addLibraryPath(m_path);
        for (const auto &name : KWin::effects->loadedEffects()) {
            if (name.startsWith(QLatin1StringView("skip-empty-spaces-native-")) && name != effectId())
                KWin::effects->unloadEffect(name);
        }
        m_loaded = KWin::effects->findEffect(effectId()) || KWin::effects->loadEffect(effectId());
        if (m_loaded) owners[effectId()] = m_owner = ++generation;
        else QCoreApplication::removeLibraryPath(m_path);
        Q_EMIT loadedChanged();
        return m_loaded;
    }
Q_SIGNALS:
    void loadedChanged();
private:
    bool m_loaded = false;
    quint64 m_owner = 0;
    QString m_path;
};

class BootstrapPlugin : public QQmlExtensionPlugin
{
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override { qmlRegisterType<Bootstrap>(uri, 1, 0, "Bootstrap"); }
};
#include "bootstrap.moc"
