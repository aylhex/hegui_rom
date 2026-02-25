/*
 * Copyright (C) 2010 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package libcore.java.lang;

import java.lang.Thread.UncaughtExceptionHandler;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;
import java.util.concurrent.locks.ReentrantLock;

import junit.framework.Assert;
import junit.framework.TestCase;

import org.mockito.InOrder;
import org.mockito.Mockito;

import libcore.java.lang.ref.FinalizationTester;

public final class ThreadTest extends TestCase {
    static {
        System.loadLibrary("javacoretests");
    }

    /**
     * getContextClassLoader returned a non-application class loader.
     * http://code.google.com/p/android/issues/detail?id=5697
     */
    public void testJavaContextClassLoader() throws Exception {
        Assert.assertNotNull("Must have a Java context ClassLoader",
                Thread.currentThread().getContextClassLoader());
    }

    public void testLeakingStartedThreads() {
        final AtomicInteger finalizedThreadsCount = new AtomicInteger();
        for (int i = 0; true; i++) {
            try {
                newThread(finalizedThreadsCount, 1024 << i).start();
            } catch (OutOfMemoryError expected) {
                break;
            }
        }
        FinalizationTester.induceFinalization();
        assertTrue("Started threads were never finalized!", finalizedThreadsCount.get() > 0);
    }

    public void testLeakingUnstartedThreads() {
        final AtomicInteger finalizedThreadsCount = new AtomicInteger();
        for (int i = 0; true; i++) {
            try {
                newThread(finalizedThreadsCount, 1024 << i);
            } catch (OutOfMemoryError expected) {
                break;
            }
        }
        FinalizationTester.induceFinalization();
        assertTrue("Unstarted threads were never finalized!", finalizedThreadsCount.get() > 0);
    }

    public void testThreadSleep() throws Exception {
        int millis = 1000;
        long start = System.currentTimeMillis();

        Thread.sleep(millis);

        long elapsed = System.currentTimeMillis() - start;
        long offBy = Math.abs(elapsed - millis);

        assertTrue("Actual sleep off by " + offBy + " ms", offBy <= 250);
    }

    public void testThreadInterrupted() throws Exception {
        Thread.currentThread().interrupt();
        try {
            Thread.sleep(0);
            fail();
        } catch (InterruptedException e) {
            assertFalse(Thread.currentThread().isInterrupted());
        }
    }

    public void testThreadSleepIllegalArguments() throws Exception {

        try {
            Thread.sleep(-1);
            fail();
        } catch (IllegalArgumentException expected) {
        }

        try {
            Thread.sleep(0, -1);
            fail();
        } catch (IllegalArgumentException expected) {
        }

        try {
            Thread.sleep(0, 1000000);
            fail();
        } catch (IllegalArgumentException expected) {
        }
    }

    public void testThreadWakeup() throws Exception {
        WakeupTestThread t1 = new WakeupTestThread();
        WakeupTestThread t2 = new WakeupTestThread();

        t1.start();
        t2.start();
        assertTrue("Threads already finished", !t1.done && !t2.done);

        t1.interrupt();
        t2.interrupt();

        Thread.sleep(1000);
        assertTrue("Threads did not finish", t1.done && t2.done);
    }

    public void testContextClassLoaderIsNotNull() {
        assertNotNull(Thread.currentThread().getContextClassLoader());
    }

    public void testContextClassLoaderIsInherited() {
        Thread other = new Thread();
        assertSame(Thread.currentThread().getContextClassLoader(), other.getContextClassLoader());
    }

    public void testUncaughtExceptionPreHandler_calledBeforeDefaultHandler() {
        UncaughtExceptionHandler initialHandler = Mockito.mock(UncaughtExceptionHandler.class);
        UncaughtExceptionHandler defaultHandler = Mockito.mock(UncaughtExceptionHandler.class);
        InOrder inOrder = Mockito.inOrder(initialHandler, defaultHandler);

        UncaughtExceptionHandler originalDefaultHandler
                = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setUncaughtExceptionPreHandler(initialHandler);
        Thread.setDefaultUncaughtExceptionHandler(defaultHandler);
        try {
            Thread t = new Thread();
            Throwable e = new Throwable();
            t.dispatchUncaughtException(e);
            inOrder.verify(initialHandler).uncaughtException(t, e);
            inOrder.verify(defaultHandler).uncaughtException(t, e);
            inOrder.verifyNoMoreInteractions();
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(originalDefaultHandler);
            Thread.setUncaughtExceptionPreHandler(null);
        }
    }

    public void testUncaughtExceptionPreHandler_noDefaultHandler() {
        UncaughtExceptionHandler initialHandler = Mockito.mock(UncaughtExceptionHandler.class);
        UncaughtExceptionHandler originalDefaultHandler
                = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setUncaughtExceptionPreHandler(initialHandler);
        Thread.setDefaultUncaughtExceptionHandler(null);
        try {
            Thread t = new Thread();
            Throwable e = new Throwable();
            t.dispatchUncaughtException(e);
            Mockito.verify(initialHandler).uncaughtException(t, e);
            Mockito.verifyNoMoreInteractions(initialHandler);
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(originalDefaultHandler);
            Thread.setUncaughtExceptionPreHandler(null);
        }
    }

    /**
     * Thread.getStackTrace() is broken. http://b/1252043
     */
    public void testGetStackTrace() throws Exception {
        Thread t1 = new Thread("t1") {
            @Override public void run() {
                doSomething();
            }
            public void doSomething() {
                try {
                    Thread.sleep(4000);
                } catch (InterruptedException ignored) {
                }
            }
        };
        t1.start();
        Thread.sleep(1000);
        StackTraceElement[] traces = t1.getStackTrace();
        StackTraceElement trace = traces[traces.length - 2];

        // Expect to find MyThread.doSomething in the trace
        assertTrue(trace.getClassName().contains("ThreadTest")
                && trace.getMethodName().equals("doSomething"));
        t1.join();
    }

    public void testGetAllStackTracesIncludesAllGroups() throws Exception {
        final AtomicInteger visibleTraces = new AtomicInteger();
        ThreadGroup group = new ThreadGroup("1");
        Thread t2 = new Thread(group, "t2") {
            @Override public void run() {
                visibleTraces.set(Thread.getAllStackTraces().size());
            }
        };
        t2.start();
        t2.join();

        // Expect to see the traces of all threads (not just t2)
        assertTrue("Must have traces for all threads", visibleTraces.get() > 1);
    }

    // http://b/27748318
    public void testNativeThreadNames() throws Exception {
        String testResult = nativeTestNativeThreadNames();
        // Not using assertNull here because this results in a better error message.
        if (testResult != null) {
            fail(testResult);
        }
    }

    // http://b/29746125
    public void testParkUntilWithUnderflowValue() throws Exception {
        final Thread current = Thread.currentThread();

        // watchdog to unpark the tread in case it will be parked
        AtomicBoolean afterPark = new AtomicBoolean(false);
        AtomicBoolean wasParkedForLongTime = new AtomicBoolean(false);
        Thread watchdog = new Thread() {
            @Override public void run() {
                try {
                    sleep(5000);
                } catch(InterruptedException expected) {}

                if (!afterPark.get()) {
                    wasParkedForLongTime.set(true);
                    LockSupport.unpark(current);
                }
            }
        };
        watchdog.start();

        // b/29746125 is caused by underflow: parkUntilArg - System.currentTimeMillis() > 0.
        // parkUntil$ should return immediately for everyargument that's <=
        // System.currentTimeMillis().
        LockSupport.parkUntil(Long.MIN_VALUE);
        if (wasParkedForLongTime.get()) {
            fail("Current thread was parked, but was expected to return immediately");
        }
        afterPark.set(true);
        watchdog.interrupt();
        watchdog.join();
    }

    /**
     * Check that call Thread.start for already started thread
     * throws {@code IllegalThreadStateException}
     */
    public void testThreadDoubleStart() {
        final ReentrantLock lock = new ReentrantLock();
        Thread thread = new Thread() {
            public void run() {
                // Lock should be acquired by the main thread and
                // this thread should block on this operation.
                lock.lock();
            }
        };
        // Acquire lock to ensure that new thread is not finished
        // when we call start() second time.
        lock.lock();
        try {
            thread.start();
            try {
                thread.start();
                fail();
            } catch (IllegalThreadStateException expected) {
            }
        } finally {
            lock.unlock();
        }
        try {
            thread.join();
        } catch (InterruptedException ignored) {
        }
    }

    /**
     * Check that call Thread.start for already finished thread
     * throws {@code IllegalThreadStateException}
     */
    public void testThreadRestart() {
        Thread thread = new Thread();
        thread.start();
        try {
            thread.join();
        } catch (InterruptedException ignored) {
        }
        try {
            thread.start();
            fail();
        } catch (IllegalThreadStateException expected) {
        }
    }

    // This method returns {@code null} if all tests pass, or a non-null String containing
    // failure details if an error occured.
    private static native String nativeTestNativeThreadNames();

    private Thread newThread(final AtomicInteger finalizedThreadsCount, final int size) {
        return new Thread() {
            long[] memoryPressure = new long[size];
            @Override protected void finalize() throws Throwable {
                super.finalize();
                finalizedThreadsCount.incrementAndGet();
            }
        };
    }

    private class WakeupTestThread extends Thread {
        public boolean done;

        public void run() {
            done = false;

            // Sleep for a while (1 min)
            try {
                Thread.sleep(60000);
            } catch (InterruptedException ignored) {
            }

            done = true;
        }
    }
}
