/*
 * Copyright (C) 2016 The Android Open Source Project
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

package libcore.dalvik.system;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import dalvik.system.BaseDexClassLoader;
import dalvik.system.DelegateLastClassLoader;
import dalvik.system.PathClassLoader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;

import libcore.io.Streams;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

@RunWith(JUnit4.class)
public final class BaseDexClassLoaderTest {
    private static class Reporter implements BaseDexClassLoader.Reporter {
        public final List<ClassLoader> classLoaders = new ArrayList<>();
        public final List<String> loadedDexPaths = new ArrayList<>();

        @Override
        public void report(List<ClassLoader> loaders, List<String> dexPaths) {
            classLoaders.addAll(loaders);
            loadedDexPaths.addAll(dexPaths);
        }

        void reset() {
            classLoaders.clear();
            loadedDexPaths.clear();
        }
    }

    private ClassLoader pcl;
    private File jar;
    private Reporter reporter;

    // For resources that we will load in this test. We're re-using parent.jar and child.jar
    // from DelegateLastClassLoaderTest for convenience.
    private Map<String, File> resourcesMap;

    @Before
    public void setupResourcesMap() throws Exception {
        resourcesMap = ClassLoaderTestSupport.setupAndCopyResources(
                Arrays.asList("parent.jar", "child.jar"));
    }

    @After
    public void cleanupResourcesMap() throws Exception {
        ClassLoaderTestSupport.cleanUpResources(resourcesMap);
    }

    @Before
    public void extractTestJar() throws Exception {
        // Extract loading-test.jar from the resource.
        pcl = BaseDexClassLoaderTest.class.getClassLoader();
        jar = File.createTempFile("loading-test", ".jar");
        try (InputStream in = pcl.getResourceAsStream("dalvik/system/loading-test.jar");
             FileOutputStream out = new FileOutputStream(jar)) {
          Streams.copy(in, out);
        }
    }

    @Before
    public void registerReporter() {
        reporter = new Reporter();
        BaseDexClassLoader.setReporter(reporter);
    }

    @After
    public void unregisterReporter() {
        BaseDexClassLoader.setReporter(null);
    }

    @After
    public void deleteTestJar() throws Exception {
        assertTrue(jar.delete());
    }

    @Test
    public void testReporting() throws Exception {
        // Load the jar file using a PathClassLoader.
        BaseDexClassLoader cl1 = new PathClassLoader(jar.getPath(),
            ClassLoader.getSystemClassLoader());

        // Verify the reported data.
        assertEquals(2, reporter.loadedDexPaths.size());
        assertEquals(2, reporter.classLoaders.size());

        // First class loader should be the one loading the files
        assertEquals(jar.getPath(), reporter.loadedDexPaths.get(0));
        assertEquals(cl1, reporter.classLoaders.get(0));

        // Second class loader should be the system class loader.
        // Don't check the actual classpath as that might vary based on system properties.
        assertEquals(ClassLoader.getSystemClassLoader(), reporter.classLoaders.get(1));
    }

    @Test
    public void testReportingUnknownLoader() throws Exception {
        // Add an unknown classloader between cl1 and the system
        ClassLoader unknownLoader = new ClassLoader(ClassLoader.getSystemClassLoader()) {};
        BaseDexClassLoader cl1 = new PathClassLoader(jar.getPath(), unknownLoader);

        assertEquals(3, reporter.loadedDexPaths.size());
        assertEquals(3, reporter.classLoaders.size());

        assertEquals(jar.getPath(), reporter.loadedDexPaths.get(0));
        assertEquals(cl1, reporter.classLoaders.get(0));

        assertNull(reporter.loadedDexPaths.get(1));
        assertEquals(unknownLoader, reporter.classLoaders.get(1));

        assertEquals(ClassLoader.getSystemClassLoader(), reporter.classLoaders.get(2));
    }

    @Test
    public void testNoReportingAfterResetting() throws Exception {
        BaseDexClassLoader cl1 = new PathClassLoader(jar.getPath(),
            ClassLoader.getSystemClassLoader());

        assertEquals(2, reporter.loadedDexPaths.size());
        assertEquals(2, reporter.classLoaders.size());

        // Check we don't report after the reporter is unregistered.
        unregisterReporter();
        reporter.reset();

        // Load the jar file using another PathClassLoader.
        BaseDexClassLoader cl2 = new PathClassLoader(jar.getPath(), pcl);

        // Verify nothing reported
        assertEquals(0, reporter.loadedDexPaths.size());
        assertEquals(0, reporter.classLoaders.size());
    }

    /* package */ static List<String> readResources(ClassLoader cl, String resourceName)
            throws Exception {
        Enumeration<URL> resources = cl.getResources(resourceName);

        List<String> contents = new ArrayList<>();
        while (resources.hasMoreElements()) {
            URL url = resources.nextElement();

            try (InputStream is = url.openStream()) {
                byte[] bytes = Streams.readFully(is);
                contents.add(new String(bytes, StandardCharsets.UTF_8));
            }
        }

        return contents;
    }

    /* package */ static String readResource(ClassLoader cl, String resourceName) throws Exception {
        InputStream in = cl.getResourceAsStream(resourceName);
        if (in == null) {
            return null;
        }

        byte[] contents = Streams.readFully(in);
        return new String(contents, StandardCharsets.UTF_8);
    }

    private void checkResources(ClassLoader loader) throws Exception {
        List<String> resources = readResources(loader, "resource.txt");

        assertEquals(2, resources.size());
        assertTrue(resources.contains("parent"));
        assertTrue(resources.contains("child"));

        resources = readResources(loader, "resource2.txt");

        assertEquals(1, resources.size());
        assertEquals("parent2", resources.get(0));
    }

    @Test
    public void testGetResourceSharedLibraries1() throws Exception {
        File parentPath = resourcesMap.get("parent.jar");
        File childPath = resourcesMap.get("child.jar");
        assertTrue(parentPath != null);
        assertTrue(childPath != null);

        ClassLoader parent = Object.class.getClassLoader();

        ClassLoader[] sharedLibraries = {
          new PathClassLoader(parentPath.getAbsolutePath(), null, parent),
          new PathClassLoader(childPath.getAbsolutePath(), null, parent),
        };

        // PCL[]{PCL[parent.jar]#PCL[child.jar]}
        ClassLoader loader = new PathClassLoader("", null, parent, sharedLibraries);
        assertEquals("parent", readResource(loader, "resource.txt"));
        checkResources(loader);

        // DLC[]{PCL[parent.jar]#PCL[child.jar]}
        loader = new DelegateLastClassLoader("", null, parent, sharedLibraries);
        assertEquals("parent", readResource(loader, "resource.txt"));
        checkResources(loader);
    }

    @Test
    public void testGetResourceSharedLibraries2() throws Exception {
        File parentPath = resourcesMap.get("parent.jar");
        File childPath = resourcesMap.get("child.jar");
        assertTrue(parentPath != null);
        assertTrue(childPath != null);

        ClassLoader parent = Object.class.getClassLoader();

        ClassLoader[] sharedLibraries = {
          new PathClassLoader(childPath.getAbsolutePath(), null, parent),
          new PathClassLoader(parentPath.getAbsolutePath(), null, parent),
        };

        // PCL[]{PCL[child.jar]#PCL[parent.jar]}
        ClassLoader loader = new PathClassLoader("", null, parent, sharedLibraries);
        assertEquals("child", readResource(loader, "resource.txt"));
        checkResources(loader);

        // DLC[]{PCL[child.jar]#PCL[parent.jar]}
        loader = new DelegateLastClassLoader("", null, parent, sharedLibraries);
        assertEquals("child", readResource(loader, "resource.txt"));
        checkResources(loader);
    }

    @Test
    public void testGetResourceSharedLibraries3() throws Exception {
        File parentPath = resourcesMap.get("parent.jar");
        File childPath = resourcesMap.get("child.jar");
        assertTrue(parentPath != null);
        assertTrue(childPath != null);

        ClassLoader parent = Object.class.getClassLoader();

        ClassLoader[] sharedLibraryLevel2 = {
          new PathClassLoader(parentPath.getAbsolutePath(), null, parent),
        };

        ClassLoader[] sharedLibraryLevel1 = {
          new PathClassLoader(childPath.getAbsolutePath(), null, parent, sharedLibraryLevel2),
        };

        // PCL[]{PCL[child.jar]{PCL[parent.jar]}}
        ClassLoader loader = new PathClassLoader("", null, parent, sharedLibraryLevel1);
        assertEquals("parent", readResource(loader, "resource.txt"));
        checkResources(loader);

        // DLC[]{PCL[child.jar]{PCL[parent.jar]}}
        loader = new DelegateLastClassLoader("", null, parent, sharedLibraryLevel1);
        assertEquals("parent", readResource(loader, "resource.txt"));
        checkResources(loader);
    }

    @Test
    public void testGetResourceSharedLibraries4() throws Exception {
        File parentPath = resourcesMap.get("parent.jar");
        File childPath = resourcesMap.get("child.jar");
        assertTrue(parentPath != null);
        assertTrue(childPath != null);

        ClassLoader parent = Object.class.getClassLoader();

        ClassLoader[] sharedLibraryLevel2 = {
          new PathClassLoader(childPath.getAbsolutePath(), null, parent),
        };

        ClassLoader[] sharedLibraryLevel1 = {
          new PathClassLoader(parentPath.getAbsolutePath(), null, parent, sharedLibraryLevel2),
        };

        // PCL[]{PCL[parent.jar]{PCL[child.jar]}}
        ClassLoader loader = new PathClassLoader("", null, parent, sharedLibraryLevel1);
        assertEquals("child", readResource(loader, "resource.txt"));
        checkResources(loader);

        // DLC[]{PCL[parent.jar]{PCL[child.jar]}}
        loader = new DelegateLastClassLoader("", null, parent, sharedLibraryLevel1);
        assertEquals("child", readResource(loader, "resource.txt"));
        checkResources(loader);
    }

    @Test
    public void testGetResourceSharedLibraries5() throws Exception {
        File parentPath = resourcesMap.get("parent.jar");
        File childPath = resourcesMap.get("child.jar");
        assertTrue(parentPath != null);
        assertTrue(childPath != null);

        ClassLoader parentParent = Object.class.getClassLoader();
        ClassLoader parent = new PathClassLoader(parentPath.getAbsolutePath(), null, parentParent);

        ClassLoader[] sharedLibrary = {
          new PathClassLoader(childPath.getAbsolutePath(), null, parentParent),
        };

        // PCL[]{PCL[child.jar]};PCL[parent.jar]
        ClassLoader pathLoader = new PathClassLoader("", null, parent, sharedLibrary);

        // Check that the parent was queried first.
        assertEquals("parent", readResource(pathLoader, "resource.txt"));

        // DLC[]{PCL[child.jar]};PCL[parent.jar]
        ClassLoader delegateLast = new DelegateLastClassLoader("", null, parent, sharedLibrary);

        // Check that the shared library was queried first.
        assertEquals("child", readResource(delegateLast, "resource.txt"));

    }
}
