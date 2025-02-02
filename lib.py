import os, re, time, \
    subprocess as sp
from icecream import ic
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
    # 'rv32gcv',
    # 'bin'
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
    # ic(compile)
    if compile['returncode']:
        # return compile
        return {
            'test_pass': False,
            'formatted_results': "\n".join([comp.replace("/home/shahzaibkashif/coding_app/api_coding_app/tmp/tmp.S", "file.S") for comp in compile["stderr"].split("\n")])
        }
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
            debug_cmds.append(f'vreg 0 {k[1:]}\n')
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
        ic("timeout here")
        return {
            "test_pass": False,
            "formatted_results": "Spike process timed out!\nMaybe the program is stuck on a loop"
        }
    with open(SIM_DEBUG_LOG) as f:
        f.readline()
        src = [
            line.strip()
            for line in f.readlines()
                if re.search(r'VLEN=[0-9]+ bits; ELEN=[0-9]+ bits', line) is None
        ]
    all_match = True
    # ic(results)
    try:
        for i, k in enumerate(results.keys()):
            if re.search(r'v[0-9]{1,2}', k) is not None:
                vec_reg_info = src[i].split()
                results[k]['src'] = [vec_reg_info[3], vec_reg_info[-1]]
            else:
                results[k]['src'] = src[i]
            results[k]['status'] = 'match' if results[k]['src'] == results[k]['ref'] else 'mismatch'
            if results[k]['status'] == 'mismatch':
                all_match = False
        ic(results)
        # formatted_results = "\n".join(
        # f"{reg}:\n  Reference:\n\t\t Hexadecimal: {result['ref']}\n\t\t Decimal: {int(result['ref'], 16)}\n  Source:\n\t\t Hexadecimal: {result['src']}\n\t\t Decimal: {int(result['src'], 16)}\n  Status: {result['status']}\n"
        # for reg, result in results.items()
        # )
        def hex_to_dec_list(hex_list):
            hex_list = hex_list[2:]
            decimal_list = []
            # ic(len(hex_list), hex_list)
            for i in range(0, len(hex_list), 8):
                decimal = int(hex_list[i:i+8], 16)
                # ic(i,decimal)
                decimal_list.append(decimal)
            # ic(decimal_list)
            return decimal_list
            # return [int(hex_list[i:i+1], 16) for i in range(0, len(hex_list), 16)]

        def format_result(result):
            if isinstance(result['ref'], list):
                ref_dec = [hex_to_dec_list(ref) for ref in result['ref']]
                src_dec = [hex_to_dec_list(src) for src in result['src']]
                ref_str = "\n\t\t ".join([f"Hexadecimal: {ref}, Decimal: {dec}" for ref, dec in zip(result['ref'], ref_dec)])
                src_str = "\n\t\t ".join([f"Hexadecimal: {src}, Decimal: {dec}" for src, dec in zip(result['src'], src_dec)])
            else:
                ref_str = f"Hexadecimal: {result['ref']}, Decimal: {int(result['ref'], 16)}"
                src_str = f"Hexadecimal: {result['src']}, Decimal: {int(result['src'], 16)}"
            return f"Reference:\n\t\t {ref_str}\n  Source:\n\t\t {src_str}\n  Status: {result['status']}\n"

        formatted_results = "\n".join(
            f"{reg}:\n  {format_result(result)}"
            for reg, result in results.items()
        )
        return {
        'formatted_results': formatted_results,
        'test_pass': all_match
        }
    except:
        read_log = open(TMP_SIM_LOG, 'r')
        log = read_log.readlines()
        read_log.close()
        return {
            'test_pass': False,
            'formatted_results': "".join(log[:100])
        }

if __name__ == '__main__':
    with open(os.path.join(ROOT, 'test.S')) as f:
        code = f.read()
    results = run_and_compare(code, {
        # 'a0': f'0x{'0' * 8}',
        # 's1': '0x000000d6',
        # f'mem[0x8{'0' * 7}]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 6}4]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 6}8]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 6}C]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}10]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}14]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}18]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}1C]': f'0x{'0' * 8}',

        # f'mem[0x8{'0' * 5}20]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}24]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}28]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}2C]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}30]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}34]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}38]': f'0x{'0' * 8}',
        # f'mem[0x8{'0' * 5}3C]': f'0x{'0' * 8}',

        

        # 'v5': ['0x000000140000000f', '0x0000000a00000005'],
        # 'v6': ['0x0000000000000000', '0x000000000000000a'],
        # 'v7': ['0x0000000000000000', '0x000000000000000a'],
        # 'v8': ['0x0000000000000000', '0x000000000000000e'],
        # 'v9': ['0x000000640000005f', '0x0000005a00000055'],

        # 'mem[0x80003000]': '0x00000005',
        # 'mem[0x80003004]': '0x0000000a',
        # 'mem[0x80003008]': '0x0000000f',
        # 'mem[0x8000300c]': '0x00000014',
        # 'mem[0x80003010]': '0x00000019',
        # 'mem[0x80003014]': '0x0000001e',
        # 'mem[0x80003018]': '0x00000023',
        # 'mem[0x8000301c]': '0x00000028',
        # 'mem[0x80003020]': '0x0000002d',
        # 'mem[0x80003024]': '0x00000032',
        # 'mem[0x80003028]': '0x00000037',
        # 'mem[0x8000302c]': '0x0000003c',
        # 'mem[0x80003030]': '0x00000041',
        # 'mem[0x80003034]': '0x00000046',
        # 'mem[0x80003038]': '0x0000004b',
        # 'mem[0x8000303c]': '0x00000050',
        # 'mem[0x80003040]': '0x00000055',
        # 'mem[0x80003044]': '0x0000005a',
        # 'mem[0x80003048]': '0x0000005f',
        # 'mem[0x8000304c]': '0x00000064',
        # 'mem[0x80000084]': '0x00000011',
        # 'mem[0x80000088]': '0x00000011',
        # 'mem[0x8000008C]': '0x00000011',
        # 'mem[0x80000090]': '0x00000011',
        # 'mem[0x80000094]': '0x00000011',
        # 'mem[0x80000098]': '0x00000011',
        # 'mem[0x8000009C]': '0x00000011',
        # 'mem[0x800000A0]': '0x00000011',
        # 'mem[0x800000A4]': '0x00000011',
        # 'mem[0x800000A8]': '0x00000011',
        # 'mem[0x800000AC]': '0x00000011',
        # 'mem[0x800000B0]': '0x00000011',
        # 'mem[0x800000B4]': '0x00000011',
        # 'mem[0x800000B8]': '0x00000011',
        # 'mem[0x800000BC]': '0x00000011',
        

        # 'a1': '0x00000000',
        'v0': ['0x0000000000000000', '0x00000000000009ca'],
        # 'v7': ['0x0000000000000000', '0x000000000000000a'],
        # 'v8': ['0x0000000000000000', '0x000000000000000a'],

        # f'mem[0x8{'0' * 5}20]': f'0x{'0' * 8}',
        # **{f'mem[0x8{"0" * 7}{i * 4:02x}]': f'0x{"0" * 8}' for i in range(8)},
        # **{f'mem[0x8{"0" * 5}20{i * 4:02x}]': f'0x{"0" * 8}' for i in range(8)},
        # **{f'v{i}': [f'0x{'0' * 16}' for _ in range(2)] for i in range(0, 10)}
    })
#     # for reg, result in results.items():
#     #     print(f'{reg}:')
#     #     print(f"  Reference: {result['ref']}")
#     #     print(f"  Source: {result['src']}")
#     #     print(f"  Status: {result['status']}\n")

    print(results)
    print(results['formatted_results'])
    print(f"Test {'passed' if results['test_pass'] else 'failed'}")
