# 非空桌面连续滑动

适用于 KWin 6.7+，使用 QML SceneEffect 绘制实时窗口缩略图。

手势开始时，按所在屏幕和当前活动找到下一个有窗口的桌面。跟手动画只绘制“起始桌面”和“目标桌面”两页，空桌面不出现在动画路径中。松手后，在动画覆盖下提交最终桌面，再完成剩余滑动；取消手势则滑回起始桌面。

支持三指、四指横向手势及首尾循环。最小化窗口算占用；面板、桌面背景、所有桌面窗口不算。固定面板保留在屏幕原位置。另一块屏幕显示自己的当前桌面，不会跟随移动。

这是 `skip-empty-spaces` 1.0 的动画替代版本，安装时需停用旧脚本和原生 `slide` 特效，避免两套动画同时执行。新特效也为普通直接桌面切换提供滑动动画。不改动 KWin 二进制，不删除或重排桌面，不移动应用窗口。

## 动画与设置入口

2.1 版使用与原生“滑动”相同的质量—弹簧—阻尼模型参数：弹簧强度 `300 / 动画速度倍率`、阻尼比 `1.1`，逐帧推进，到达像素级停止阈值后结束；取消手势使用相同的缓动返回。桌面间距、背景是否移动和系统动画速度会在安装时从原生设置读取。

弹簧使用独立的解析解实现；KWin 原生实现使用数值积分，因此两者渲染和采样不会逐帧完全相同。两页实时窗口视图仍由本特效绘制，以便让空桌面完全离开滑动路径。

2.1.1 版由正在滑动的屏幕在场景同步前推进弹簧，绘制结束后排队请求该屏幕的下一帧，替代独立的 `FrameAnimation` 时钟。不同刷新率的屏幕不共享动画帧计时；静止的副屏不持续请求动画帧。

因此入口是“桌面特效 → 非空桌面连续滑动”。旧的“手势切换跳过空桌面”KWin 脚本采用切换后补跳，可能闪过空桌面；安装工具会将其停用，不要再与本特效同时启用。

更改原生“滑动”的间距、背景设置或系统动画速度后，可同步到本特效：

```sh
/usr/bin/python3 tools/sync_settings.py
```

## 安装与验证

需要 KDE Plasma / KWin 6.7+、Python 3.9+、`kpackagetool6`、`kwriteconfig6`、`kreadconfig6` 和 `qdbus6`。安装及实机检查工具还需要 `dbus-python` 和 PyGObject；运行逻辑测试需要 Node.js。

```sh
git clone https://github.com/leychan/skip-empty-spaces-smooth.git
cd skip-empty-spaces-smooth
node tests/navigation.test.cjs
node tests/plan.test.cjs
node tests/spring.test.cjs
python3 -m unittest discover -s tests -p '*_test.py'
/usr/bin/python3 tools/check_live.py
python3 tools/package.py
/usr/bin/python3 tools/install.py
```

安装包生成在仓库内的 `dist/skip-empty-spaces-smooth.zip`，不依赖克隆目录的位置。`check_live.py` 需要在已登录的 KWin 桌面会话中运行。

安装工具会核对 KWin **实际运行的构建编号**。若同一会话的 QML 缓存仍返回旧组件，会使用内容哈希生成新的加载地址，避免文件已更新而动画仍是旧版。设置里仍只保留一个“非空桌面连续滑动”入口，内部 ID 可能带有 `-runtime-<哈希>` 后缀；无需重启 KWin。同步设置和恢复工具会自动识别这个 ID。

安装工具会启用本特效，停用旧的 `skip-empty-spaces` 脚本以及原生 `slide` 渲染器，使用新动画替代它们。失败时会尝试恢复此前的运行状态，不启动无关脚本。回退旧版时读取本机已安装包，不要求保留旧项目源码。

安装包类型是 `KWin/Effect`，启用入口在系统设置 → 桌面特效 → “非空桌面连续滑动”。目前支持横向一行排列；其他全屏特效（例如概览）开启时由 KWin 决定特效优先级。触控板取消、快速反向以及不同缩放比例的设备仍应结合实际使用检查。

如需恢复原生动画，执行：

```sh
/usr/bin/python3 tools/restore_native.py
```

恢复原生动画不会启用旧版的二次补跳脚本。

验证记录（2026-10-27）：2.0 版已完成 55 项导航测试、QML 加载和截图渲染检查，用户确认可连贯跳过空桌面。2.1 版新增 6 项弹簧连续性与刷新率测试；Python 共 9 项打包、回退、设置继承及 QML 缓存构建校验测试。70 项自动测试通过。已排查同会话热更新仍运行旧 180 毫秒组件的问题，并核对实际运行的弹簧构建编号。

2.1.1 实机诊断：在 240 Hz 内屏、60 Hz 副屏组合上，同画面匀速滑动对照从约 88 次/秒绘制、95% 间隔不超过 26 ms，改善到约 237 次/秒、95% 间隔不超过 5 ms。正式弹簧的完成与取消均验证到正确终点；内屏约 235–238 次/秒绘制，副屏约 62 次/秒绘制。这些数值来自离屏 QQuickWindow 的绘制回调，**不等同于显示器实际呈现帧率**。主观手感仍需实际触控板确认。

可复现的短时测量（临时显示动画，不切换实际桌面，结束后自动清理诊断特效）：

```sh
/usr/bin/python3 tools/benchmark_live.py --output eDP-1
/usr/bin/python3 tools/benchmark_live.py --output HDMI-A-1 --cancel
```

将屏幕名称替换为本机名称。`--driver timeline` 与 `--driver render` 使用相同的两秒匀速运动，分别对照独立时钟与按屏幕绘制推进。

接口：[SceneEffect](https://api.kde.org/qml-org-kde-kwin-sceneeffect.html)、[WindowThumbnail](https://api.kde.org/qml-org-kde-kwin-windowthumbnail.html)、[SwipeGestureHandler](https://api.kde.org/qml-org-kde-kwin-swipegesturehandler.html)。

原生动画参数依据：[KWin SlideEffect](https://invent.kde.org/plasma/kwin/-/blob/Plasma/6.7/src/plugins/slide/slide.cpp)、[原生滑动配置](https://invent.kde.org/plasma/kwin/-/blob/Plasma/6.7/src/plugins/slide/slide.kcfg)。
