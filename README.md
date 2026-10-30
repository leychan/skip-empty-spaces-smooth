# 非空桌面连续滑动

适用于 KWin 6.7，触控板三指或四指横向滑动时，直接滑向所在屏幕的下一个非空桌面。空桌面不进入动画路径；最小化窗口计为占用，面板、桌面背景、固定到所有桌面的窗口不计为占用。

3.0 版直接在 KWin 场景中绘制原窗口和壁纸，改变绘制位置并裁剪到当前屏幕。它不创建整屏窗口缩略图，也不经过 Qt Quick 离屏画面的二次采样。125% 等分数缩放下的位置按物理像素对齐；静止副屏保持自己的桌面与绘制路径。

桌面特效中的 QML 入口只负责加载、校验和卸载原生模块，不显示 SceneView、不接管键盘或鼠标。无需替换 KWin 系统二进制，不删除或重排桌面，不移动应用窗口。安装工具会停用原生 `slide` 和旧版 `skip-empty-spaces` 二次补跳脚本。

## 动画

使用独立解析解实现的弹簧，强度为 `300 / 动画速度倍率`，阻尼比为 `1.1`。每个动画帧直接读取 KWin 的预计呈现时间，保留纳秒计时精度。松手时从最后 50 毫秒的手势样本估计速度，接续朝目标桌面的运动，并限制初速度以避免越过目标或回弹；停顿后松手不会使用过期速度。页面到达终点像素后交回正常桌面绘制。

只为起始页和目标页保留跨桌面可见性，避免其他桌面的应用在动画期间无谓重绘。固定面板和所有桌面窗口保留在原位置。玻璃和背景对比度的临时绘制标记会在动画结束时恢复。

间距、背景是否移动和系统动画速度会在安装时从原生“滑动”设置读取。修改原生设置后执行：

```sh
/usr/bin/python3 tools/sync_settings.py
```

## 安装

需要正在运行的 KWin 6.7、**相同版本的 KWin 开发头文件与库**、CMake、Ninja、C++20 编译器、Qt 6 QML/DBus/Widgets 和相应 KDE Frameworks 开发包，以及 Python 3.9+、`dbus-python`、`kpackagetool6`、`kwriteconfig6`、`kreadconfig6`、`qdbus6`。KWin 插件不保证 ABI 稳定，升级 KWin 后应重新构建；原生模块会拒绝不同 KWin 版本的加载。

```sh
git clone https://github.com/leychan/skip-empty-spaces-smooth.git
cd skip-empty-spaces-smooth
/usr/bin/python3 tools/install.py
/usr/bin/python3 tools/check_native.py
```

安装工具自动编译原生模块并运行 C++ 核心测试。构建产物和完整安装包保存在 `dist/`，不进入 Git；模块只安装到当前用户的特效目录，不改动系统插件目录，也不需要管理员安装权限。所有源码均位于仓库内，原生模块与其余源码使用 MIT 许可。

安装会核对 QML 入口和原生模块**实际运行的构建编号**。若同一会话仍缓存旧组件，会使用带哈希的运行目录重新加载；设置中保留一个“非空桌面连续滑动”入口，无需重启 KWin。内部模块 ID 为 `skip-empty-spaces-native-<哈希>`，由入口管理生命周期，不应单独启用。

KWin 升级后，请重新运行 `tools/install.py`，按当前开发库重新编译。构建编号包含 KWin、Qt 版本和目标架构，升级依赖后的安装会使用新的原生模块标识。若出现能切换桌面但没有动画，可先运行 `tools/check_native.py` 检查模块是否加载。

## 验证与诊断

```sh
node tests/navigation.test.cjs
node tests/plan.test.cjs
node tests/spring.test.cjs
node tests/pixels.test.cjs
python3 -m unittest discover -s tests -p '*_test.py'
/usr/bin/python3 tools/check_native.py --output eDP-1 --benchmark
/usr/bin/python3 tools/trace_live.py
```

将屏幕名称替换为本机名称。原生核心测试覆盖 6152 种占用布局、首尾循环与边界、不同刷新率下的弹簧、松手速度连续性、过期样本和高速滑动不越过目标。`--benchmark` 只预览滑回当前桌面的动画，不切换实际桌面；报告合成绘制次数，不保证每次绘制都等同于实际显示器呈现帧。

原生清晰度对照：`tools/check_native.py --output eDP-1 --compare` 拍摄真实桌面与零位移原生预览的截图。可附加 `--crop x1,y1,x2,y2` 比较指定静态区域的像素差异（需要 Pillow）。此项还需 `flameshot`；正常使用特效不需要截图工具。生命周期诊断仅在内存保留最近 48 条时间记录，不包含窗口内容。

2026-10-27 的本机验证：240 Hz / 125% 内屏上，原生合成绘制约 240 次/秒；选取的静态文字区域与真实桌面截图逐像素一致。用户已确认整屏模糊消失、跳过空桌面正常，松手后的衔接与减速更自然。

`tools/check_live.py`、`tools/preview_live.py`、`tools/benchmark_live.py` 和 `tools/package.py --qml-only` 用于旧版 QML 渲染器的回归与对照，不代表默认安装包的原生绘制路径。当前支持横向一行桌面；其他全屏特效开启时尊重 KWin 的特效优先级。

## 恢复原生“滑动”

```sh
/usr/bin/python3 tools/restore_native.py
```

入口卸载时会自动清理其原生渲染模块；恢复工具不会重新启用旧版二次补跳脚本。

接口与参数依据：[KWin Effect API](https://api.kde.org/kwin/html/classKWin_1_1Effect.html)、[KWin SlideEffect](https://invent.kde.org/plasma/kwin/-/blob/Plasma/6.7/src/plugins/slide/slide.cpp)、[原生滑动配置](https://invent.kde.org/plasma/kwin/-/blob/Plasma/6.7/src/plugins/slide/slide.kcfg)。
