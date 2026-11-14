[app]

# Application title (shown on the launcher, Arabic is fine on Android)
title = مدير الديون

# Package identity
package.name = debtmanagerpro
package.domain = com.debtmanagerpro

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,ttf,otf,json,txt,md,spec
source.include_patterns = assets/*,core/*,database/*,services/*,ui/*,workers/*,reports/*,android/*
source.exclude_dirs = tests,bin,.git,__pycache__,.pytest_cache,build,dist,.venv,venv,vendor,artifacts,.github,api_server
source.exclude_patterns = *.pyc,*.db,*.db-wal,*.db-shm,.env,.ui_review.py

version = 1.0.0

# KivyMD is a pure Python package, the two Arabic text helpers are pure Python as
# well, so python-for-android installs them through pip.
requirements = python3,kivy==2.3.1,kivymd==1.2.0,arabic-reshaper==3.0.0,python-bidi==0.6.6

orientation = portrait
fullscreen = 0

# Android
android.api = 34
# minSdk 23 is required by the project brief (Android 6.0+).
android.minapi = 23
android.ndk_api = 23
# NDK r28c refuses to compile CPython for API 23 (preadv/pwritev are not declared
# for that API level), so the build pins the NDK release python-for-android
# supports for a minSdk 23 target.
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.private_storage = True
android.allow_backup = True
android.logcat_filters = *:S python:D

# Only permissions that phase 1/2 actually need. SMS/CALL/contacts permissions are
# intentionally NOT declared yet: they are added (and requested at runtime) in the
# messaging phase. See android/README.md for the per-version rules.
android.permissions = android.permission.INTERNET,android.permission.POST_NOTIFICATIONS

[buildozer]
log_level = 2
warn_on_root = 1
