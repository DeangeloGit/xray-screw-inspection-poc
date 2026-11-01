#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <wchar.h>
#include <stdio.h>

int wmain(int argc, wchar_t **argv) {
    wchar_t root[32768], python[32768], script[32768], command[65536];
    DWORD length = GetModuleFileNameW(NULL, root, 32768);
    if (!length || length >= 32768) return 1;
    wchar_t *slash = wcsrchr(root, L'\\');
    if (!slash) return 1;
    *slash = L'\0';
    if (_snwprintf(python, 32768, L"%ls\\runtime\\python.exe", root) < 0 ||
        _snwprintf(script, 32768, L"%ls\\_app\\portable_entry.py", root) < 0) return 1;
    if (GetFileAttributesW(python) == INVALID_FILE_ATTRIBUTES || GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(NULL, L"Please extract the complete ZIP folder before running XRayReview.exe. Keep runtime and _app next to this EXE.", L"XRay Review", MB_OK | MB_ICONERROR);
        return 2;
    }
    const wchar_t *option = argc == 2 && wcscmp(argv[1], L"--self-test") == 0 ? L" --self-test" : L"";
    if (_snwprintf(command, 65536, L"\"%ls\" -X utf8 \"%ls\"%ls", python, script, option) < 0) return 1;
    SetConsoleOutputCP(CP_UTF8);
    wprintf(L"XRay Review - Windows x64 portable edition\nKeep this window open while using the app.\n\n");
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    if (!CreateProcessW(python, command, NULL, NULL, TRUE, 0, NULL, root, &startup, &process)) {
        wchar_t error[256];
        _snwprintf(error, 256, L"Cannot start the bundled runtime. Windows error: %lu", GetLastError());
        MessageBoxW(NULL, error, L"XRay Review", MB_OK | MB_ICONERROR);
        return 3;
    }
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    if (code != 0 && option[0] == L'\0') {
        wprintf(L"\nStartup/test failed (exit %lu). See logs\\startup.log or run DIAGNOSTICS.bat.\nPress Enter to close.\n", code);
        getchar();
    }
    return (int)code;
}
