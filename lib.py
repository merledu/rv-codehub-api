import os, re, time, \
    subprocess as sp

ROOT = os.path.dirname(
    os.path.abspath(__file__)
)
TMP = os.path.join(ROOT, 'tmp')
TMP_CODE_FILE = os.path.join(TMP, 'tmp.S')
TMP_ELF_FILE = os.path.join(TMP, 'tmp.elf')
TMP_SIM_LOG = os.path.join(TMP, 'tmp.log')
SIM_DEBUG_LOG = os.path.join(TMP, 'sim_debug.log')
SIM_DEBUG_CMD = os.path.join(ROOT, 'spike_debug_cmd.txt')
LINKER_SCRIPT = os.path.join(ROOT, 'link.ld')
RISCV32_GNU_TOOLCHAIN = os.path.join(
    os.environ['RISCV_GNU_TOOLCHAIN'],
    'rv32gcv',
    'bin'
)
RISCV_SIM = os.environ['SPIKE_PATH']
os.environ['PATH'] = os.pathsep.join((
    RISCV32_GNU_TOOLCHAIN,
    RISCV_SIM,
    os.environ['PATH']
))
INT_REG_ABI_NAMES = [
    'zero',
    'ra',
    'sp',
    'gp',
    'tp'
] + [
    f't{i}'
    for i in range(3)
] + [
    f's{i}'
    for i in range(2)
] + [
    f'a{i}'
    for i in range(8)
] + [
    f's{i}'
    for i in range(2, 12)
] + [
    f't{i}'
    for i in range(3, 7)
]
VEC_REGS = [
    f'v{i}'
    for i in range(32)
]

def compile_code(code):
    if not os.path.exists(
        os.path.join(TMP)
    ):
        os.mkdir(TMP)
    with open(TMP_CODE_FILE, 'w') as f:
        f.write(code)
    compile_result = sp.run(
        ['riscv32-unknown-elf-gcc',
         '-static',
         '-nostdlib',
         '-nostartfiles',
         '-g',
         '-march=rv32gcv',
         '-mabi=ilp32d',
         '-mcmodel=medany',
         '-fvisibility=hidden',
         '-T', LINKER_SCRIPT,
         '-o', TMP_ELF_FILE,
         TMP_CODE_FILE],
        capture_output = True,
        text = True
    )
    return {
        'returncode': compile_result.returncode,
        'stdout': compile_result.stdout,
        'stderr': compile_result.stderr
    }

def run_and_compare(code, ref):
    '''ref format: {
        'int_reg_ABI': '0x00000000',
        'mem[0x00000000]': '0x00000000',
        'vector_reg (v0-v31)': ['0x0000000000000000', '0x0000000000000000'] ([element 1, element 0])
    }'''
    compile = compile_code(code)
    if compile['returncode']:
        return compile
    debug_cmds = [f'untiln insn 0 0x{'0' * 8}\n']
    results = {}
    for k, v in ref.items():
        if k in INT_REG_ABI_NAMES:
            debug_cmds.append(f'reg 0 {k}\n')
            results[k] = {'ref': v}
        elif re.search(r'mem\[0x[0-9a-fA-F]{8}\]', k) is not None:
            debug_cmds.append(f'mem {k[4: -1]}\n')
            results[k] = {'ref': v}
        elif re.search(r'v[0-9]{1,2}', k) is not None:
            debug_cmds.append(f'vreg 0 {k}\n')
            results[k] = {'ref': v}
        else:
            return {'err': 'Invalid reference format'}
    debug_cmds.append('q')
    with open(SIM_DEBUG_CMD, 'w') as f:
        f.writelines(debug_cmds)
    try:
        sim_debug_log = open(SIM_DEBUG_LOG, 'w')
        sp.run(
            ['spike',
             '-d',
             '-l',
             f'--log={TMP_SIM_LOG}',
             f'--debug-cmd={SIM_DEBUG_CMD}',
             '--isa=rv32gcv',
             TMP_ELF_FILE],
            stdout = sim_debug_log,
            stderr = sp.STDOUT,
            text = True,
            timeout = 5
        )
        sim_debug_log.close()
    except sp.TimeoutExpired:
        sim_debug_log.close()
    with open(SIM_DEBUG_LOG) as f:
        f.readline()
        src = [
            line.strip()
            for line in f.readlines()
                if re.search(r'VLEN=[0-9]+ bits; ELEN=[0-9]+ bits', line) is None
        ]
    for i, k in enumerate(results.keys()):
        if re.search(r'v[0-9]{1,2}', k) is not None:
            vec_reg_info = src[i].split()
            results[k]['src'] = [vec_reg_info[3], vec_reg_info[-1]]
        else:
            results[k]['src'] = src[i]
        results[k]['status'] = 'match' if results[k]['src'] == results[k]['ref'] \
            else 'mismatch'
    return results

if __name__ == '__main__':
    with open(os.path.join(ROOT, 'test.S')) as f:
        code = f.read()
    results = run_and_compare(code, {
        'a0': f'0x{'0' * 8}',
        'a1': f'0x{'0' * 8}',
        f'mem[0x8{'0' * 7}]': f'0x{'0' * 8}',
        'v0': [
            f'0x{'0' * 16}'
            for _ in range(2)
        ]
    })
    print(f'\n{results = }')
