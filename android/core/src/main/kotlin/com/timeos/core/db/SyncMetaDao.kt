package com.timeos.core.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface SyncMetaDao {

    @Query("SELECT * FROM sync_meta WHERE id = ${SyncMetaEntity.SINGLETON_ID}")
    suspend fun get(): SyncMetaEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(meta: SyncMetaEntity)
}
