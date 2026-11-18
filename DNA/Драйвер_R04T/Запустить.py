#!/usr/bin/env python3
"""Загрузить исходные модели и запустить переданный пример ngspice."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parent
SPICE = ROOT / 'spice'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def download(url):
    print('Загрузка:', url, flush=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(request, timeout=40).read()


def models():
    cfg = json.loads((SPICE/'модели.json').read_text())
    directory = SPICE/'models'; directory.mkdir(exist_ok=True)
    for name in ['2N5551.LIB', '2N5401.LIB', 'AD8055_archive.cir']:
        spec = cfg[name]; path = directory/name
        if not path.exists():
            data = download(spec['url'])
            if name == 'AD8055_archive.cir':
                text = data.decode('latin1').replace('\r\n','\n').replace('\r','\n'); i = text.lower().index('.subckt ad8055')
                start = text.rfind('***** AD8055', 0, i)
                end = text.lower().index('.ends', i)+len('.ends')
                assert start >= 0
                data = (text[start:end]+'\n').encode('latin1')
            if sha(data) != spec['sha256']:
                raise RuntimeError('Изменился файл модели: '+name)
            path.write_bytes(data)
        if sha(path.read_bytes()) != spec['sha256']:
            raise RuntimeError('Не совпал SHA256: '+name)
    output = directory/'output_pair.lib'
    if not output.exists():
        spec = cfg['Qucs']; inputs = []
        for key in ['library', 'properties']:
            item = spec[key]; data = download(item['url'])
            if sha(data) != item['sha256']:
                raise RuntimeError('Изменился исходник Qucs: '+key)
            inputs.append(data.decode())
        library, props = inputs
        properties = re.findall(r'Props.push_back\(qucs::Property\("([^"]+)"', props)
        assert len(properties) == 48
        lines = ['* Перенос параметров из библиотеки Qucs; не модели ST.',
                 '* BD140: семейство BD136/138/140, в исходнике Tf=0.',
                 '* Высокочастотная точность этой выходной пары не подтверждена.']
        for source, target in [('BD139', 'Qucs_BD139'), ('BD136', 'Qucs_BD136_138_140')]:
            block = re.search(r'<Component '+source+r'>([\s\S]*?)</Component>', library)[1]
            vals = re.findall(r'"([^"]*)"', re.search(r'<_BJT[^>]+>', block)[0])
            assert len(vals) == len(properties)
            p = dict(zip(properties, (v.strip() for v in vals)))
            assert p['Area'] == '1' and p['Kb'] == '0' and p['Kf'] == '0'
            omit = {'Type', 'Temp', 'Ffe', 'Kb', 'Ab', 'Fb', 'Area'}
            lines.append('.model '+target+' '+p['Type']+'(')
            lines += ['+ '+k+'='+v for k, v in p.items() if k not in omit]
            lines.append('+ )')
        lines.append('.model D4148 D(Is=2.52n Rs=.568 N=1.752 Cjo=4p M=.4 tt=20n)')
        output.write_text('\n'.join(lines)+'\n')
    assert sha(output.read_bytes()) == cfg['output_pair.lib']['sha256'], 'Изменилась выходная модель'
    print('Модели готовы; контрольные суммы совпали.', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--подготовить', action='store_true', help='Только загрузить модели')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--постоянный', action='store_true', help='Рабочая точка при задании 11,3 В')
    g.add_argument('--без-фильтра', action='store_true', help='Подать чистую кусочно-линейную форму')
    p.add_argument('--таймаут', type=int, default=600, help='Ограничение времени ngspice, с')
    args = p.parse_args(); models()
    if args.подготовить: return
    binary = shutil.which('ngspice')
    if binary is None: raise SystemExit('Установите ngspice и добавьте его в PATH. Модели уже готовы.')
    name = 'dc' if args.постоянный else 'ideal' if args.без_фильтра else 'waveform'
    text = (SPICE/(name+'.cir')).read_text()
    text = re.sub(r'(?im)^\.end\s*$', '', text)
    text += '\n.control\nset wr_singlescale\nset wr_vecnames\nset numdgt=12\nrun\nwrdata result_'+name+'.txt v(vin) v(out) v(preout) v(drive) v(up) v(down)\nquit\n.endc\n.end\n'
    runfile = 'run_'+name+'.cir'
    (SPICE/runfile).write_text(text)
    (SPICE/('result_'+name+'.txt')).unlink(missing_ok=True)
    try:
        result = subprocess.run([binary, '-b', runfile], cwd=SPICE, capture_output=True, text=True, timeout=args.таймаут)
    except subprocess.TimeoutExpired as e:
        raise SystemExit('Истекло время расчёта; результат не принимается. Увеличьте --таймаут.') from e
    log = result.stdout+result.stderr
    (SPICE/('result_'+name+'.log')).write_text(log)
    if result.returncode or re.search(r'abort|Error:|timestep too small|no such vector', log, re.I):
        raise SystemExit('Ошибка ngspice. Подробности: spice/result_'+name+'.log')
    data = SPICE/('result_'+name+'.txt')
    last = data.read_text().splitlines()[-1].split()
    if name != 'dc' and abs(float(last[0])-64e-6) > 1e-12:
        raise SystemExit('Расчёт не дошёл до 64 мкс; результат не принимается.')
    print('Готово:', data.relative_to(ROOT), flush=True)
    print('Ток через R16: (v(preout)−v(out))/6,8 Ом. Включает ток ООС и утечки после R16.')


if __name__ == '__main__':
    main()
