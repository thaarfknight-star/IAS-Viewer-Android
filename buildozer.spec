[app]

# (str) Title of your application
title = IAS Viewer

# (str) Package name
package.name = IASViewer

# (str) Package domain (needed for android/ios packaging)
package.domain = org.iasviewer

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include not the exclusion)
source.include_exts = py,png,jpg,jpeg,webp,ttf,json,txt

# (str) Application version
version = 2.0.80

# (list) Application requirements
# kivy: UI | opencv: پخش زنده‌ی دوربین (RTSP/HTTP) | numpy/pillow: فریم
# arabic-reshaper + python-bidi: نمایش درست متن فارسی در Kivy
# (1.0.0) پین charset-normalizer حذف شد — نسخه‌ی 3.4.1 با Python 3.14
# ناسازگار بود؛ حالا آخرین نسخه‌ی سازگار خودکار انتخاب می‌شود.
requirements = python3,kivy,opencv,numpy,pillow,arabic-reshaper,python-bidi

# (str) Supported orientations: landscape, portrait, sensor, all ...
orientation = landscape

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (list) Android permissions
# INTERNET برای اتصال به استریم دوربین‌ها (RTSP/HTTP) لازم است.
android.permissions = INTERNET

# (int) Target Android API (33 = Android 13)
android.api = 33

# (int) Minimum Android API
android.minapi = 24

# (int) Numeric versionCode for the APK. The real value comes from the
# APP_ANDROID_NUMERIC_VERSION env var set by the workflow (buildozer
# replaces config tokens with matching env vars); this is only a fallback.
# Needed because version.txt is like '2.0.80-beta' and p4a cannot turn the
# '-beta' suffix into a number (int('80-beta') crashes make_package).
android.numeric_version = 102420080

# (bool) Automatically accept Android SDK licenses during the build
# (وگرنه نصب build-tools با «license is not accepted» می‌میرد)
android.accept_sdk_license = True

# (bool) enables Android auto backup feature (Android API >=23)
android.backup_rules =

# (str) The format used to package the app for release mode (aab or apk)
# android.release_artifact = aab

# (str) Android architecture to build for
# android.archs = arm64-v8a, armeabi-v7a

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
# (رفع عیب‌یابی بیلد) سطح ۲ = خروجی کامل python-for-android در لاگ؛ اگر بیلد
# دوباره fail شد، خطای واقعی p4a (نه فقط «Command failed») دیده می‌شود.
log_level = 2

# (str) Path to build artifact storage, for example:
#    /home/user/.buildozer
# (default: <home>/.buildozer)
# buildozer_dir =

# (str) Path to build output (i.e. .apk, .aab) storage
# bin_dir = ./bin

# (bool) Allow skipping the git clone of python-for-android, and use
# an already existing clone instead.
# p4a.fork =

# (str) python-for-android branch to use
# p4a.branch = master
