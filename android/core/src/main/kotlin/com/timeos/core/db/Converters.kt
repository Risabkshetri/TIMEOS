package com.timeos.core.db

import androidx.room.TypeConverter
import org.json.JSONArray
import org.json.JSONObject

/** Room type converters for the two structured fields on [EventEntity]. */
class Converters {

    @TypeConverter
    fun fromStringList(value: List<String>): String = JSONArray(value).toString()

    @TypeConverter
    fun toStringList(value: String): List<String> {
        if (value.isEmpty()) return emptyList()
        val arr = JSONArray(value)
        return (0 until arr.length()).map { arr.getString(it) }
    }

    @TypeConverter
    fun fromStringMap(value: Map<String, String>): String = JSONObject(value as Map<*, *>).toString()

    @TypeConverter
    fun toStringMap(value: String): Map<String, String> {
        if (value.isEmpty()) return emptyMap()
        val obj = JSONObject(value)
        return obj.keys().asSequence().associateWith { obj.getString(it) }
    }
}
