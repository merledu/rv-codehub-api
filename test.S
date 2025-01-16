.global _start
_start:
    li a0, 0x2200 # MSTATUS_VS & (MSTATUS_VS >> 1)
    csrs mstatus, a0
    csrwi vcsr, 0

    la sp, __stacktop

    // no ra to save
    call test

    // exit
    li a0, 0x80000000
    li a1, -1
    sw a1, 4(a0)
    csrwi vcsr, 0

    .p2align 2

.global test
test:
    addi x1, x1, 1
    li a0, 0x400
    li a1, 0xc1
    li a2, 2
    vsetvl x0, a0, a1
    lui x30, 1
    auipc x31, 0

zvbb_test:
    addi     x3,x0,10
    vsetvli x5,x3,e32,m1,tu,mu
    addi     x2,x0,121
    vadd.vi v2, v1,10
    vadd.vx v3, v2, x2
    vadd.vv v4,v2,v3
    vadd.vv v5,v2,v2
    vadd.vi v2, v1,7



will_not_be_executed:
    vadd.vv v2, v1, v1