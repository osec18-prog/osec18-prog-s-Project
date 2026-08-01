plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "ph.edu.aics.campusconnect_app"
    compileSdk = flutter.compileSdkVersion

    // The Android Gradle Plugin resolves an NDK at configure time. Letting it
    // auto-download leaves a broken empty folder ("did not have a
    // source.properties file"), so the NDK is installed up front with:
    //   sdkmanager "ndk;28.2.13676358"
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "ph.edu.aics.campusconnect_app"
        // mobile_scanner (ML Kit barcode scanning) needs API 21+; Flutter's
        // default is already higher, so just follow it.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}
