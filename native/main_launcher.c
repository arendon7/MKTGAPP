#include <errno.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static volatile sig_atomic_t child_pid = -1;

static void forward_signal(int signo) {
    pid_t pid = (pid_t)child_pid;
    if (pid > 0) kill(pid, signo);
}

static int path_join(char *out, size_t out_size, const char *base, const char *suffix) {
    int n = snprintf(out, out_size, "%s/%s", base, suffix);
    return n >= 0 && (size_t)n < out_size ? 0 : -1;
}

static int parent_dir(char *path) {
    char *slash = strrchr(path, '/');
    if (!slash || slash == path) return -1;
    *slash = '\0';
    return 0;
}

static int copy_path(char *out, size_t out_size, const char *value) {
    int n = snprintf(out, out_size, "%s", value);
    return n >= 0 && (size_t)n < out_size ? 0 : -1;
}

static int fail(const char *message) {
    fprintf(stderr, "BINARIO Marketing launch failed: %s\n", message);
    return 5;
}

static const char *launchservices_probe_path(int argc, char **argv) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (strcmp(argv[i], "--launchservices-probe") == 0) return argv[i + 1];
    }
    return NULL;
}

static int write_probe(const char *path) {
    FILE *handle = fopen(path, "w");
    if (!handle) return fail("cannot write LaunchServices probe");
    if (fputs("ok\n", handle) == EOF || fclose(handle) != 0) return fail("cannot persist LaunchServices probe");
    return 0;
}

int main(int argc, char **argv) {
    char executable[PATH_MAX];
    uint32_t size = (uint32_t)sizeof(executable);
    if (_NSGetExecutablePath(executable, &size) != 0) return fail("cannot resolve executable path");

    char macos_dir[PATH_MAX];
    if (!realpath(executable, macos_dir)) return fail("cannot canonicalize executable path");
    if (parent_dir(macos_dir) != 0) return fail("cannot resolve Contents/MacOS");

    char contents_dir[PATH_MAX];
    if (copy_path(contents_dir, sizeof(contents_dir), macos_dir) != 0) return fail("bundle path is too long");
    if (parent_dir(contents_dir) != 0) return fail("cannot resolve Contents");

    char resources[PATH_MAX], python_bin[PATH_MAX], python_dir[PATH_MAX];
    char media_bin[PATH_MAX], transcription_bin[PATH_MAX], whisper_cli[PATH_MAX];
    char whisper_model[PATH_MAX], ffmpeg[PATH_MAX], ffprobe[PATH_MAX];
    char keychain_helper[PATH_MAX], launch_py[PATH_MAX], path_env[PATH_MAX * 3];

    if (path_join(resources, sizeof(resources), contents_dir, "Resources") ||
        path_join(python_bin, sizeof(python_bin), resources, "runtime/python/bin/python3") ||
        path_join(python_dir, sizeof(python_dir), resources, "runtime/python/bin") ||
        path_join(media_bin, sizeof(media_bin), resources, "runtime/media/bin") ||
        path_join(transcription_bin, sizeof(transcription_bin), resources, "runtime/transcription/bin") ||
        path_join(whisper_cli, sizeof(whisper_cli), transcription_bin, "whisper-cli") ||
        path_join(whisper_model, sizeof(whisper_model), resources, "runtime/transcription/models/ggml-tiny.bin") ||
        path_join(ffmpeg, sizeof(ffmpeg), media_bin, "ffmpeg") ||
        path_join(ffprobe, sizeof(ffprobe), media_bin, "ffprobe") ||
        path_join(keychain_helper, sizeof(keychain_helper), macos_dir, "binario-meta-keychain") ||
        path_join(launch_py, sizeof(launch_py), resources, "launch.py")) {
        return fail("bundle path is too long");
    }

    if (access(python_bin, X_OK) != 0) return fail("embedded Python runtime missing");
    if (access(ffmpeg, X_OK) != 0 || access(ffprobe, X_OK) != 0) return fail("embedded media runtime missing");
    if (access(whisper_cli, X_OK) != 0 || access(whisper_model, R_OK) != 0) return fail("embedded transcription runtime missing");
    if (access(keychain_helper, X_OK) != 0) return fail("Meta Keychain helper missing");
    if (access(launch_py, R_OK) != 0) return fail("launch bootstrap missing");

    const char *probe = launchservices_probe_path(argc, argv);
    if (probe) return write_probe(probe);

    int path_len = snprintf(path_env, sizeof(path_env), "%s:%s:%s:/usr/bin:/bin", media_bin, transcription_bin, python_dir);
    if (path_len < 0 || (size_t)path_len >= sizeof(path_env)) return fail("cannot build PATH");

    setenv("PATH", path_env, 1);
    setenv("BINARIO_FFMPEG", ffmpeg, 1);
    setenv("BINARIO_FFPROBE", ffprobe, 1);
    setenv("BINARIO_WHISPER_CLI", whisper_cli, 1);
    setenv("BINARIO_WHISPER_MODEL", whisper_model, 1);
    setenv("BINARIO_META_KEYCHAIN_HELPER", keychain_helper, 1);
    setenv("PYTHONNOUSERSITE", "1", 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
    unsetenv("PYTHONHOME");
    unsetenv("PYTHONPATH");

    signal(SIGINT, forward_signal);
    signal(SIGTERM, forward_signal);
    signal(SIGHUP, forward_signal);

    char *python_argv[] = {python_bin, "-I", "-B", launch_py, NULL};
    pid_t pid = 0;
    int rc = posix_spawn(&pid, python_bin, NULL, NULL, python_argv, environ);
    if (rc != 0) {
        fprintf(stderr, "BINARIO Marketing launch failed: posix_spawn: %s\n", strerror(rc));
        return 5;
    }
    child_pid = pid;

    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno == EINTR) continue;
        return fail("cannot wait for embedded runtime");
    }
    child_pid = -1;

    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return 5;
}
