plugins {
    // Android Gradle plugin 9.5.0 (October 2026): Gradle 9.6.0, JDK 17, build tools 36.0.0,
    // API levels up to 37 (developer.android.com/build/releases/agp-9-5-0-release-notes,
    // read 2026-11-24)
    id("com.android.application") version "9.5.0"
}

android {
    namespace = "bau.watch"
    compileSdk = 36
    defaultConfig {
        applicationId = "bau.watch"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation(project(":tunnel"))
}
