/* Run check_parsimony.py to compare SSE, legacy AVX, and hybrid kernels.
   -ffunction-sections -fdata-sections -Wl,--gc-sections drops unused PLL entrypoints. */
#include "../../pll/fastDNAparsimony.c"
#include <stddef.h>

static uint64_t rng_state = UINT64_C(0x48e5ac716393d2b1);
static uint32_t next_u32(void) {
    rng_state ^= rng_state << 13; rng_state ^= rng_state >> 7; rng_state ^= rng_state << 17;
    return (uint32_t)rng_state;
}
static uint64_t digest = UINT64_C(1469598103934665603);
static void mix(uint64_t x) { digest ^= x; digest *= UINT64_C(1099511628211); }

int main(void) {
    const int states_list[] = {2,4,7,20,32};
    const int lengths[] = {0,1,2,31,32,33,63,64,65,127,128,129,255,256,257,511,512,513,1024};
    unsigned long tested = 0, bounds = 0;
    printf("layout %zu %zu %zu %zu %zu %zu %zu\n",sizeof(pllInstance),sizeof(pInfo),sizeof(node),
        offsetof(pInfo,parsimonyLength),offsetof(pInfo,parsVect),offsetof(pllInstance,parsimonyScore),offsetof(pllInstance,randomNumberSeed));
    for(size_t si=0;si<sizeof(states_list)/sizeof(states_list[0]);++si)
    for(size_t li=0;li<sizeof(lengths)/sizeof(lengths[0]);++li)
    for(int trial=0;trial<40;++trial) {
        const int states=states_list[si], n=lengths[li];
        const uint32_t all=states==32?UINT32_MAX:((UINT32_C(1)<<states)-1);
        size_t words=(n+31)/32;
        size_t width=(words+INTS_PER_VECTOR-1)/INTS_PER_VECTOR*INTS_PER_VECTOR;
        pllInstance tr={0};pInfo part={0};pInfo*parts[]={&part};partitionList pr={0};
        unsigned int score[8]={0};int ti[]={8,4,3,0,4,1,2,0};
        uint32_t masks[3][1024];uint32_t parent[1024];
        part.states=states;part.parsimonyLength=width;
        size_t entries=width*states*8;
        if(posix_memalign((void**)&part.parsVect,PLL_BYTE_ALIGNMENT,(entries?entries:1)*sizeof(parsimonyNumber)))return 2;
        memset(part.parsVect,0,(entries?entries:1)*sizeof(parsimonyNumber));
        pr.partitionData=parts;pr.numberOfPartitions=1;
        tr.parsimonyScore=score;tr.ti=ti;
        unsigned expected_sub=0,expected_full=0;
        for(int p=0;p<n;++p) {
            for(int tip=0;tip<3;++tip) {
                uint32_t r=next_u32();
                masks[tip][p]=(r%5)?(UINT32_C(1)<<(r%states)):(next_u32()&all);
                if(!masks[tip][p])masks[tip][p]=all;
            }
            uint32_t shared=masks[0][p]&masks[1][p];
            expected_sub+=shared==0;
            parent[p]=shared?shared:(masks[0][p]|masks[1][p]);
            expected_full+=(shared==0)+((parent[p]&masks[2][p])==0);
        }
        for(int tip=0;tip<3;++tip)
        for(size_t p=0;p<width*32;++p) {
            uint32_t mask=p<(size_t)n?masks[tip][p]:all;
            for(int state=0;state<states;++state)if(mask&(UINT32_C(1)<<state))
                part.parsVect[width*states*(tip+1)+width*state+p/32]|=UINT32_C(1)<<(p%32);
        }
        newviewParsimonyIterativeFast(&tr,&pr);
        if(score[4]!=expected_sub){fprintf(stderr,"subscore mismatch\n");return 3;}
        for(size_t p=0;p<width*32;++p)for(int state=0;state<states;++state) {
            unsigned actual=(part.parsVect[width*states*4+width*state+p/32]>>(p%32))&1;
            unsigned expected=((p<(size_t)n?parent[p]:all)>>state)&1;
            if(actual!=expected){fprintf(stderr,"partial bit mismatch\n");return 4;}
        }
        ti[0]=4;tr.bestParsimony=UINT_MAX;
        unsigned actual=evaluateParsimonyIterativeFast(&tr,&pr);
        if(actual!=expected_full){fprintf(stderr,"full score mismatch\n");return 5;}
        mix(actual);mix(score[4]);
        for(unsigned bound=0;bound<=expected_full+1;++bound) {
            tr.bestParsimony=bound;actual=evaluateParsimonyIterativeFast(&tr,&pr);
            if((actual<bound)!=(expected_full<bound)||
               (actual<bound&&actual!=expected_full)) {
                fprintf(stderr,"bound decision mismatch states%d n%d threshold%u actual%u exact%u\n",states,n,bound,actual,expected_full);return 6;
            }
            mix(actual<bound);++bounds;
        }
        free(part.parsVect);++tested;
    }
    printf("PASS cases%lu bound_decisions%lu hash%016llx\n",tested,bounds,(unsigned long long)digest);
    return 0;
}
