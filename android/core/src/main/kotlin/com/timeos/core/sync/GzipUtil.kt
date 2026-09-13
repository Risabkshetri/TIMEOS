package com.timeos.core.sync

import java.io.ByteArrayOutputStream
import java.util.zip.GZIPOutputStream

object GzipUtil {
    fun gzip(input: ByteArray): ByteArray {
        val out = ByteArrayOutputStream()
        GZIPOutputStream(out).use { it.write(input) }
        return out.toByteArray()
    }
}
