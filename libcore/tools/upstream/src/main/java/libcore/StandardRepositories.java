/*
 * Copyright (C) 2017 The Android Open Source Project
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

package libcore;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import libcore.Repository.OjluniRepository;

import static libcore.Repository.openJdk9;
import static libcore.Repository.openJdkLegacy;

public class StandardRepositories {

    private final List<Repository> allUpstreams;
    // upstreams older than what is currently the default
    private final List<Repository> historicUpstreams;
    private final Repository openJdk8u121;
    private final Repository openJdk9b113;
    private final Repository openJdk7u40;
    private final OjluniRepository ojluni;

    private StandardRepositories(Path buildTop, Path upstreamRoot) {
        // allUpstreams is ordered from latest to earliest
        Set<Repository> allUpstreams = new LinkedHashSet<>();
        allUpstreams.add(openJdk9(upstreamRoot, "9+181"));
        this.openJdk9b113 = addAndReturn(allUpstreams, openJdk9(upstreamRoot, "9b113+"));
        this.openJdk8u121 = addAndReturn(allUpstreams, openJdkLegacy(upstreamRoot, "8u121-b13"));
        Repository openJdk8u60 = addAndReturn(allUpstreams, openJdkLegacy(upstreamRoot, "8u60"));
        this.openJdk7u40 = addAndReturn(allUpstreams, openJdkLegacy(upstreamRoot, "7u40"));
        this.allUpstreams = Collections.unmodifiableList(new ArrayList<>(allUpstreams));
        this.historicUpstreams = Collections.unmodifiableList(new ArrayList<>(
                Arrays.asList(openJdk8u60, openJdk7u40)
        ));
        this.ojluni = new OjluniRepository(buildTop);
    }

    private static Repository addAndReturn(Set<Repository> repositories, Repository repository) {
        repositories.add(repository);
        return repository;
    }

    public List<Repository> historicUpstreams() {
        return historicUpstreams;
    }

    public OjluniRepository ojluni() {
        return ojluni;
    }

    /**
     * Returns all upstream repository snapshots, in order from latest to earliest.
     */
    public List<Repository> upstreams() {
        return allUpstreams;
    }

    public static StandardRepositories fromEnv() {
        Path androidBuildTop = Paths.get(getEnvOrThrow("ANDROID_BUILD_TOP"));
        Path upstreamRoot = Paths.get(getEnvOrThrow("OPENJDK_HOME"));
        return new StandardRepositories(androidBuildTop, upstreamRoot);
    }

    private static String getEnvOrThrow(String name) {
        String result = System.getenv(name);
        if (result == null) {
            throw new IllegalStateException("Environment variable undefined: " + name);
        }
        return result;
    }

    private static final Set<String> juFilesFromJsr166 = Collections.unmodifiableSet(
            new HashSet<>(Arrays.asList(
                    "AbstractQueue",
                    "ArrayDeque",
                    "ArrayPrefixHelpers",
                    "Deque",
                    "Map",
                    "NavigableMap",
                    "NavigableSet",
                    "PriorityQueue",
                    "Queue",
                    "SplittableRandom"
            )));

    public boolean isJsr166(Path relPath) {
        boolean result = relPath.startsWith("java/util/concurrent/");
        String ju = "java/util/";
        String suffix = ".java";
        if (!result && relPath.startsWith(ju)) {
            String name = relPath.toString().substring(ju.length());
            if (name.endsWith(suffix)) {
                name = name.substring(0, name.length() - suffix.length());
                result = juFilesFromJsr166.contains(name);
            }
        }
        return result;
    }

    public Repository referenceUpstreamAsOfAndroidP(Path relPath) {
        boolean isJsr166 = isJsr166(relPath);
        if (isJsr166) {
            return openJdk9b113;
        } else if (relPath.startsWith("java/sql/") || relPath.startsWith("javax/sql/")) {
            return openJdk7u40;
        } else {
            return openJdk8u121;
        }
    }

}
