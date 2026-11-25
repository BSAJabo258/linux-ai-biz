plugins {
    `java-library`
}

java {
    // Android's build needs JDK 17 (Android Gradle plugin 9.5 release notes, read 2026-11-24)
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

dependencies {
    // JSch, mwiede's maintained fork: Revised BSD (its pom, read 2026-11-24)
    api("com.github.mwiede:jsch:2.28.8")
    testImplementation(platform("org.junit:junit-bom:5.14.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    // The real-server test runs only where an OpenSSH server and BAU are installed
    // (BAU_SSHD_TEST=1); the others run everywhere.
    environment("BAU_SSHD_TEST", System.getenv("BAU_SSHD_TEST") ?: "")
    testLogging { events("passed", "skipped", "failed") }
}
