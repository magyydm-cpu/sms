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
# Python is pinned to the newest release Kivy 2.3.1 supports (its default is
# 3.14, which Kivy 2.3.1 predates). python-bidi is pinned to its last pure-Python
# release: 0.6.x is a Rust extension that cannot be cross-built for Android here.
requirements = python3==3.13.5,hostpython3==3.13.5,kivy==2.3.1,kivymd==1.2.0,arabic-reshaper==3.0.0,python-bidi==0.4.2

orientation = portrait
fullscreen = 0

# Android
android.api = 34
# minSdk 23 is required by the project brief (Android 6.0+).
android.minapi = 23
# bionic only declares preadv/pwritev from API 24, and CPython's remote_debugging
# source needs them, so the NDK target is API 24 while the manifest keeps
# minSdk 23 (the app still installs on Android 6.0).
android.ndk_api = 24
# NDK r28c ships clang 19 and breaks the python3 recipe; 25b is the release
# python-for-android is tested with.
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
# The p4a release on PyPI leaves a mixed pip inside its build venv and then
# "pip install -U pip" fails with ImportError: open_rich_spinner. Commit d2ee8c5
# (kivy/python-for-android#3360) clears the venv instead of self-upgrading pip.
p4a.branch = develop
p4a.commit = d2ee8c5
