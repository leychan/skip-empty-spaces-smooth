# 非空桌面连续滑动

适用于 KWin 6.7+，使用 QML SceneEffect 绘制实时窗口缩略图。

手势开始时，按所在屏幕和当前活动找到下一个有窗口的桌面。跟手动画只绘制“起始桌面”和“目标桌面”两页，空桌面不出现在动画路径中。松手后，在动画覆盖下提交最终桌面，再完成剩余滑动；取消手势则滑回起始桌面。

支持三指、四指横向手势及首尾循环。最小化窗口算占用；面板、桌面背景、所有桌面窗口不算。固定面板保留在屏幕原位置。另一块屏幕显示自己的当前桌面，不会跟随移动。

这是 `skip-empty-spaces` 1.0 的动画替代版本，安装时需停用旧脚本和原生 `slide` 特效，避免两套动画同时执行。新特效也为普通直接桌面切换提供滑动动画。不改动 KWin 二进制，不删除或重排桌面，不移动应用窗口。

## 安装与验证

需要 KDE Plasma / KWin 6.7+、Python 3.9+、`kpackagetool6`、`kwriteconfig6`。安装及实机检查工具还需要 `dbus-python` 和 PyGObject；运行逻辑测试需要 Node.js。

```sh
git clone https://github.com/leychan/skip-empty-spaces-smooth.git
cd skip-empty-spaces-smooth
node tests/navigation.test.cjs
node tests/plan.test.cjs
python3 -m unittest discover -s tests -p '*_test.py'
/usr/bin/python3 tools/check_live.py
python3 tools/package.py
/usr/bin/python3 tools/install.py
```

安装包生成在仓库内的 `dist/skip-empty-spaces-smooth.zip`，不依赖克隆目录的位置。`check_live.py` 需要在已登录的 KWin 桌面会话中运行。

安装工具会启用本特效，停用旧的 `skip-empty-spaces` 脚本以及原生 `slide` 渲染器，使用新动画替代它们。失败时会尝试恢复此前的运行状态，不启动无关脚本。回退旧版时读取本机已安装包，不要求保留旧项目源码。

安装包类型是 `KWin/Effect`，启用入口在系统设置 → 桌面特效 → “非空桌面连续滑动”。目前支持横向一行排列；其他全屏特效（例如概览）开启时由 KWin 决定特效优先级。触控板取消、快速反向以及不同缩放比例的设备仍应结合实际使用检查。

如需恢复原生动画，执行：

```sh
kwriteconfig6 --file kwinrc --group Plugins --key skip-empty-spaces-smoothEnabled false
kwriteconfig6 --file kwinrc --group Plugins --key slideEnabled true
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.unloadEffect skip-empty-spaces-smooth
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.loadEffect slide
```

恢复原生动画不会启用旧版的二次补跳脚本。

验证记录（2026-10-27）：55 项方向、占用、循环、多屏、取消和预览目标测试通过；真实 KWin 6.7.4 中 QML 主文件和窗口视图实例化通过；临时特效渲染与本机截图确认动画直接绘制起始桌面及非空目标桌面；启用后用户实测反馈“符合预期，动画连贯”。临时预览特效已自动卸载，不保留在启用列表中。

接口：[SceneEffect](https://api.kde.org/qml-org-kde-kwin-sceneeffect.html)、[WindowThumbnail](https://api.kde.org/qml-org-kde-kwin-windowthumbnail.html)、[SwipeGestureHandler](https://api.kde.org/qml-org-kde-kwin-swipegesturehandler.html)。
