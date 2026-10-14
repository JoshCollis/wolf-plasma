#!/usr/bin/env python3
"""Compile and exercise the EXACT fixed-mode function, not a reimplementation."""
from pathlib import Path
import subprocess, sys, tempfile
source = Path(sys.argv[1])
text=source.read_text()
func=text[text.index('Bool\nxwl_randr_add_modes_fixed('):text.index('\nvoid\nxwl_output_set_mode_fixed(')]
preamble='''#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <assert.h>
typedef int Bool;
#define FALSE 0
#define TRUE 1
#define ARRAY_SIZE(a) (sizeof(a)/sizeof(a[0]))
#define xallocarray(n,s) calloc(n,s)
#define ErrorF(...) fprintf(stderr,__VA_ARGS__)
typedef void* RRModePtr;
struct xwl_output {int mode_width,mode_height; void* randr_output;};
uint32_t FakeScreenFps;
static double expected;
static int count;
const int32_t xwl_output_fake_modes[][2]={{1920,1200},{1920,1080},{1280,720}};
RRModePtr xwayland_cvt(int w,int h,double rate,int a,int b) {
 if(rate!=expected) {fprintf(stderr,"FAIL mode %dx%d: %.3f != %.3f Hz\\n",w,h,rate,expected); exit(1);}
 count++; return (void*)1;
}
int mode_sort(const void*a,const void*b) {return 0;}
void RROutputSetModes(void*a,void*b,int c,int d) {}
'''
main='''int main(void) {
 struct xwl_output out={0};
 unsigned rates[]={0,60,90,120,144};
 for(unsigned i=0;i<5;i++) {
   FakeScreenFps=rates[i]; expected=rates[i]?rates[i]:60;
   for(int j=0;j<2;j++) {
     count=0;
     assert(xwl_randr_add_modes_fixed(&out,j?1912:1920,j?1192:1200));
     assert(count==(j?4:3));
   }
 }
 puts("PASS: exact fixed-mode C path at default/60/90/120/144, listed and unlisted geometry");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as temp:
    c=Path(temp)/'test.c'; exe=Path(temp)/'test'; c.write_text(preamble+func+main)
    subprocess.run(['gcc','-std=c11','-Wall','-Werror',str(c),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
