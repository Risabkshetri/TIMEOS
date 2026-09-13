package com.timeos.core.model

/**
 * TimeOS event-type registry subset collected on Android in Phase 1B
 * (docs/TIMEOS_ENGINEERING_SPEC.md §9.2, §8.1). COLLECTOR_START/STOP/HEALTH are reserved for
 * later phases' observability work and are not emitted yet.
 */
enum class EventType {
    APP_FOREGROUND,
    APP_BACKGROUND,
    SCREEN_ON,
    SCREEN_OFF,
    DEVICE_LOCK,
    DEVICE_UNLOCK,
    USER_INTERACTION,
    DEVICE_STARTUP,
    DEVICE_SHUTDOWN,
    COLLECTOR_START,
    COLLECTOR_STOP,
    HEALTH,
}
