// BAU Watch, the tablet app (docs/TABLET.md): the app and its tunnel library.
// -PtunnelOnly builds and tests the tunnel alone (no Android tools needed).
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "bau-watch"
include(":tunnel")
if (providers.gradleProperty("tunnelOnly").orNull == null) {
    include(":app")
}
