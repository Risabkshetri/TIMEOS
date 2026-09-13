package com.timeos.core.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.TypeConverters

/**
 * Phase 2's local database (docs/TIMEOS_ENGINEERING_SPEC.md §38 Phase 2). Version 1 is the
 * baseline schema — this is the first Room version ever shipped, so there is no prior version to
 * migrate from yet. Future schema changes must add a real Migration and a migration test (see
 * core/src/androidTest/.../MigrationTest.kt) rather than relying on destructive fallback.
 */
@Database(
    entities = [EventEntity::class, SyncBatchEntity::class, SyncMetaEntity::class],
    version = 1,
    exportSchema = true,
)
@TypeConverters(Converters::class)
abstract class TimeOSDatabase : RoomDatabase() {
    abstract fun eventDao(): EventDao
    abstract fun syncBatchDao(): SyncBatchDao
    abstract fun syncMetaDao(): SyncMetaDao

    companion object {
        private const val DB_NAME = "timeos.db"

        @Volatile
        private var instance: TimeOSDatabase? = null

        fun getInstance(context: Context): TimeOSDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    TimeOSDatabase::class.java,
                    DB_NAME,
                ).build().also { instance = it }
            }
    }
}
