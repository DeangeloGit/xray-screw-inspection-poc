/* Host-side CRC verification of the same miniz extractor and appended payload. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "miniz.h"
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    FILE *file=fopen(argv[1],"rb");if(!file)return 3;
    fseek(file,0,SEEK_END);long total=ftell(file);if(total<24)return 4;
    fseek(file,total-24,SEEK_SET);char magic[16];uint64_t size=0;
    if(fread(magic,1,16,file)!=16 || fread(&size,1,8,file)!=8)return 5;
    fclose(file);if(memcmp(magic,"XRAYSFX-00000001",16)!=0 || size>(uint64_t)total-24)return 6;
    mz_zip_archive zip;memset(&zip,0,sizeof(zip));
    if(!mz_zip_reader_init_file_v2(&zip,argv[1],0,total-24-size,size))return 7;
    if(!mz_zip_validate_archive(&zip,0))return 8;
    printf("PASS: miniz validates all %u embedded file CRCs\n",mz_zip_reader_get_num_files(&zip));
    mz_zip_reader_end(&zip);return 0;
}
