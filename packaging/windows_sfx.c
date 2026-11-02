#ifndef UNICODE
#define UNICODE
#endif
#include <windows.h>
#include <shlobj.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <wchar.h>
#include "miniz.h"
#include "sfx_bundle.h"

#define CAP 32768
static wchar_t problem[1024];
static int fail(const wchar_t *text) {
    _snwprintf(problem,1024,L"%ls\nWindows error: %lu\nNo Mac or network connection is required. This app needs permission to write its local app-data folder and run its bundled Python.",text,GetLastError());
    MessageBoxW(NULL,problem,L"XRay Review - startup error",MB_OK|MB_ICONERROR);
    return 1;
}
static int directories(wchar_t *input) {
    wchar_t long_path[CAP];
    if(wcslen(input)+5>=CAP)return 0;
    _snwprintf(long_path,CAP,L"\\\\?\\%ls",input);
    wchar_t *path=long_path;
    for (wchar_t *p=path+7;*p;p++) {
        if (*p==L'\\') { *p=0;BOOL ok=CreateDirectoryW(path,NULL);DWORD e=GetLastError();*p=L'\\';if(!ok && e!=ERROR_ALREADY_EXISTS)return 0; }
    }
    return CreateDirectoryW(path,NULL) || GetLastError()==ERROR_ALREADY_EXISTS;
}
static size_t write_file(void *opaque,mz_uint64 offset,const void *buffer,size_t length) {
    FILE *file=(FILE*)opaque;
    if (_fseeki64(file,offset,SEEK_SET)!=0)return 0;
    return fwrite(buffer,1,length,file);
}
static int safe_name(const char *name) {
    if(!name[0] || name[0]=='/' || name[0]=='\\' || strchr(name,':') || strchr(name,'\\'))return 0;
    const char *p=name;
    while(*p) {
        const char *end=strchr(p,'/');size_t n=end?(size_t)(end-p):strlen(p);
        if((n==1 && p[0]=='.') || (n==2 && p[0]=='.' && p[1]=='.'))return 0;
        if(!end)break;p=end+1;
    }
    return 1;
}
int wmain(int argc,wchar_t **argv) {
    wchar_t self[CAP],base[CAP],version[CAP],root[CAP],marker[CAP],target[CAP],parent[CAP];
    if(!GetModuleFileNameW(NULL,self,CAP))return fail(L"Cannot find this EXE.");
    if(FAILED(SHGetFolderPathW(NULL,CSIDL_LOCAL_APPDATA|CSIDL_FLAG_CREATE,NULL,0,base)))return fail(L"Cannot locate local app data.");
    if(wcslen(base)>CAP-1024)return fail(L"App-data path is too long.");
    wcscat(base,L"\\XRayReview");
    _snwprintf(version,CAP,L"%ls\\versions\\%ls",base,XRAY_BUNDLE_ID);
    _snwprintf(root,CAP,L"%ls\\%ls",version,XRAY_BUNDLE_ROOT);
    _snwprintf(marker,CAP,L"%ls\\complete.marker",version);
    wchar_t mutex_name[160];_snwprintf(mutex_name,160,L"Local\\XRayReview-extract-%ls",XRAY_BUNDLE_ID);
    HANDLE mutex=CreateMutexW(NULL,FALSE,mutex_name);
    if(!mutex)return fail(L"Cannot create extraction lock.");
    DWORD waited=WaitForSingleObject(mutex,120000);
    if(waited!=WAIT_OBJECT_0 && waited!=WAIT_ABANDONED){CloseHandle(mutex);return fail(L"Another copy is still preparing the app. Please retry shortly.");}
    SetConsoleOutputCP(CP_UTF8);
    wprintf(L"XRay Review - self-contained Windows CPU edition\nNo Python installation, Mac connection, or network download is required.\n");
    if(GetFileAttributesW(marker)==INVALID_FILE_ATTRIBUTES) {
        wprintf(L"Preparing bundled runtime (first launch)...\n");fflush(stdout);
        if(!directories(version)){ReleaseMutex(mutex);CloseHandle(mutex);return fail(L"Cannot create the app-data cache.");}
        HANDLE file=CreateFileW(self,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
        LARGE_INTEGER size;
        if(file==INVALID_HANDLE_VALUE || !GetFileSizeEx(file,&size) || size.QuadPart<24)return fail(L"Cannot read this EXE.");
        HANDLE mapping=CreateFileMappingW(file,NULL,PAGE_READONLY,0,0,NULL);
        unsigned char *view=(unsigned char*)MapViewOfFile(mapping,FILE_MAP_READ,0,0,0);
        if(!view)return fail(L"Cannot open bundled payload.");
        unsigned char *footer=view+(size_t)size.QuadPart-24;
        uint64_t zip_size=0;memcpy(&zip_size,footer+16,8);
        if(memcmp(footer,"XRAYSFX-00000001",16)!=0 || zip_size>(uint64_t)size.QuadPart-24)return fail(L"This EXE payload is incomplete. Copy the complete file again.");
        mz_zip_archive zip;memset(&zip,0,sizeof(zip));
        if(!mz_zip_reader_init_mem(&zip,footer-zip_size,(size_t)zip_size,0))return fail(L"Cannot read the bundled ZIP.");
        mz_uint count=mz_zip_reader_get_num_files(&zip);
        for(mz_uint i=0;i<count;i++) {
            mz_zip_archive_file_stat stat;
            if(!mz_zip_reader_file_stat(&zip,i,&stat) || !safe_name(stat.m_filename))return fail(L"Invalid bundled file name.");
            wchar_t name[CAP];int chars=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,stat.m_filename,-1,name,CAP);
            if(!chars || wcslen(version)+(size_t)chars+2>=CAP)return fail(L"A bundled path is invalid or too long.");
            for(wchar_t *p=name;*p;p++)if(*p==L'/')*p=L'\\';
            _snwprintf(target,CAP,L"%ls\\%ls",version,name);
            wcscpy(parent,target);wchar_t *slash=wcsrchr(parent,L'\\');if(slash)*slash=0;
            if(!directories(parent))return fail(L"Cannot create a bundled directory.");
            if(mz_zip_reader_is_file_a_directory(&zip,i)){if(!directories(target))return fail(L"Cannot create a bundled directory.");continue;}
            wchar_t long_target[CAP];_snwprintf(long_target,CAP,L"\\\\?\\%ls",target);
            FILE *output=_wfopen(long_target,L"wb");
            if(!output)return fail(L"Cannot write a bundled file. Check the local folder permissions.");
            mz_bool ok=mz_zip_reader_extract_to_callback(&zip,i,write_file,output,0);fclose(output);
            if(!ok)return fail(L"Bundled file verification failed. Copy the complete EXE again.");
        }
        mz_zip_reader_end(&zip);UnmapViewOfFile(view);CloseHandle(mapping);CloseHandle(file);
        FILE *done=_wfopen(marker,L"wb");if(!done)return fail(L"Cannot save extraction status.");fputs("complete",done);fclose(done);
    }
    ReleaseMutex(mutex);CloseHandle(mutex);
    SetEnvironmentVariableW(L"XRAY_USER_ROOT",base);
    _snwprintf(target,CAP,L"%ls\\XRayReview.exe",root);
    wchar_t command[CAP+64];
    const wchar_t *option=argc==2 && wcscmp(argv[1],L"--self-test")==0 ? L" --self-test" : L"";
    _snwprintf(command,CAP+64,L"\"%ls\"%ls",target,option);
    STARTUPINFOW startup={0};PROCESS_INFORMATION process={0};startup.cb=sizeof(startup);
    wprintf(L"Data directory: %ls\n",base);fflush(stdout);
    if(!CreateProcessW(target,command,NULL,NULL,TRUE,0,NULL,root,&startup,&process))return fail(L"Cannot start the extracted app. An endpoint policy may be blocking the executable.");
    WaitForSingleObject(process.hProcess,INFINITE);DWORD code=1;GetExitCodeProcess(process.hProcess,&code);
    CloseHandle(process.hThread);CloseHandle(process.hProcess);
    return (int)code;
}
