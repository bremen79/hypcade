/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;
import java.nio.ByteBuffer;
/** Native bounded access-unit parser; called only by the decoder thread. */
public final class Mpeg2PacketReader {
    private Mpeg2PacketReader() {}
    public static native long open(String path, long offset, byte[] header) throws java.io.IOException;
    public static native long read(long handle, ByteBuffer buffer) throws java.io.IOException;
    public static native void close(long handle);
}
