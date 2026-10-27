// SPDX-License-Identifier: MIT
import QtQuick
import org.kde.kwin 3.0 as KWin
import "../native" as Native

// This inactive package entry owns the native renderer's lifetime. It creates
// no SceneViews and never intercepts keyboard or pointer input.
KWin.SceneEffect {
    visible: false
    readonly property string buildId: "@SKIP_EMPTY_BUILD@"
    readonly property bool nativeLoaded: bootstrap.loaded
    readonly property string nativeId: bootstrap.effectId

    Native.Bootstrap {
        id: bootstrap
        Component.onCompleted: {
            if (!load(Qt.resolvedUrl("../plugins/")))
                console.error("The occupied spaces native renderer could not load");
        }
    }
}
