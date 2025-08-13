// Firefox configuration to force X11 mode and prevent Wayland fallback
// This file is used by the HTML debug overlay to ensure Firefox starts quickly

// Force X11 backend
pref("media.ffmpeg.vaapi.enabled", false);
pref("media.ffmpeg.vaapi.force-disabled", true);
pref("media.ffmpeg.vaapi.force-disabled-reason", "forced-x11-mode");

// Disable Wayland
pref("widget.wayland.enabled", false);
pref("widget.wayland.force-disabled", true);

// Disable GPU acceleration that might cause delays
pref("layers.acceleration.force-enabled", false);
pref("layers.acceleration.disabled", true);
pref("webgl.disabled", true);
pref("webgl.force-enabled", false);

// Disable sandboxing that can cause startup delays
pref("security.sandbox.content.level", 0);
pref("security.sandbox.logging.enabled", false);

// Optimize for fast startup
pref("browser.startup.homepage_welcome_url", "");
pref("browser.startup.homepage_welcome_url.additional", "");
pref("browser.startup.page", 0);
pref("browser.startup.homepage", "about:blank");

// Disable unnecessary features
pref("extensions.autoDisableScopes", 0);
pref("extensions.shownSelectionUI", true);
pref("browser.newtabpage.enabled", false);
pref("browser.newtabpage.activity-stream.enabled", false);

// Force X11 rendering
pref("gfx.canvas.azure.accelerated", false);
pref("gfx.canvas.azure.accelerated.win", false);
pref("gfx.canvas.azure.accelerated.layers", false);

// Disable telemetry and other background processes
pref("toolkit.telemetry.enabled", false);
pref("toolkit.telemetry.unified", false);
pref("browser.ping-centre.telemetry", false);
pref("dom.ipc.plugins.reportCrashURL", false);
