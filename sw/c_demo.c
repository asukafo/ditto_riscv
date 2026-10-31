/* Freestanding LP64 C: no libc, no multiply/divide, no privileged instructions. */
static volatile unsigned char bytes[8] = {0x80, 0x7f, 0, 1, 2, 3, 4, 5};
static volatile short halves[2] = {-30000, 1234};
static volatile unsigned int words[2] = {0xffffffffu, 0};
static volatile long history[4];
static const long values[4] = {1, 2, 3, 4};

__attribute__((noinline)) static long transform(long x) {
    return (x << 1) + 3;
}

__attribute__((noinline)) static long compute(const long *input, int count) {
    long (*volatile function)(long) = transform; /* force indirect JALR calls */
    long sum = 0;
    for (int i = 0; i < count; ++i)
        sum += function(input[i]);
    return sum;
}

int main(void) {
    if (history[0] || history[1] || history[2] || history[3])
        return -1;
    long total = compute(values, 4); /* 5 + 7 + 9 + 11 = 32 */
    bytes[2] = (unsigned char)(bytes[0] ^ 0x5a); /* 218 */
    halves[1] = (short)(halves[1] + 3);         /* 1237 */
    words[1] = words[0] + 2u;                  /* defined unsigned wrap: 1 */
    history[0] = total;
    history[1] = (signed char)bytes[0];
    history[2] = halves[0];
    history[3] = words[1];
    return (int)(total + bytes[2] + halves[1] + words[1]); /* 1488 */
}
