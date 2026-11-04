/* Native RV64IMAC C: real M arithmetic, A atomics, compressed code and CSR read. */
static volatile long counter=5;
static volatile long inputs[4]={7,-9,-63,5};
__attribute__((noinline)) static long multiply(long a,long b) { return a*b; }
__attribute__((noinline)) static long divide(long a,long b) { return a/b; }
__attribute__((noinline)) static long remainder(long a,long b) { return a%b; }
int main(void) {
    unsigned long isa;
    __asm__ volatile ("csrr %0,misa" : "=r"(isa));
    if ((isa & 0x1105ul)!=0x1105ul) return -1;
    long old=__atomic_fetch_add(&counter,7,__ATOMIC_SEQ_CST);
    long expected=12;
    int changed=__atomic_compare_exchange_n(&counter,&expected,20,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);
    volatile unsigned int word=0xffffffffu;
    word+=2u;
    return (int)(1000+old+counter+changed+multiply(inputs[0],inputs[1])+divide(inputs[2],inputs[3])+remainder(inputs[2],inputs[3])+word); /* 949 */
}
