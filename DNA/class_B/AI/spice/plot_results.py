"""Plot existing ngspice data.txt; no surrogate circuit model or time alignment."""
from pathlib import Path
import os, json, re
HERE = Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(HERE/'.matplotlib'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    source=HERE/'data.txt'
    if not source.exists():raise SystemExit('Run ngspice first: data.txt is missing.')
    log=(HERE/'spice.log').read_text(errors='replace')
    if 'Compatibility modes selected: ps' not in log:
        raise SystemExit('PSpice compatibility not confirmed. Check .spiceinit and spice.log.')
    if re.search(r'(?im)^\s*(error\b|fatal\b|.*analysis.*aborted|.*timestep too small)',log):
        raise SystemExit('SPICE reported an error. Inspect spice.log before plotting.')
    names=source.open(encoding='utf8').readline().split()
    data=np.loadtxt(source,skiprows=1,ndmin=2)
    if data.shape[1]!=len(names) or not np.isfinite(data).all():raise SystemExit('Malformed/nonfinite SPICE output.')
    col={n:data[:,i] for i,n in enumerate(names)}
    t=col['time'];vin=col['v(vin)'];out=col['v(hv_wave)'];current=col['i(VLOAD)']
    if not np.all(np.diff(t)>0) or not np.isclose(t[-1],112.5e-6,rtol=0,atol=1e-12):
        raise SystemExit('Incomplete or unexpected transient: expected stop 112.5 us.')
    target=17.92*vin-2.8;error=out-target
    np.savetxt(HERE/'waveforms.csv',np.column_stack([t,vin,target,out,error,current]),delimiter=',',
               header='time_s,vin_v,vtarget_v,vout_v,error_v,load_current_a',comments='',fmt='%.12g')
    for filename,start,stop,title in [('waveforms.png',0,112.5e-6,'Full run: settling + 3 pulses'),
                                      ('last_pulse.png',75e-6,102.5e-6,'Third pulse (no time alignment)')]:
        mask=(t>=start-1e-15)&(t<=stop+1e-15);x=(t[mask]-start)*1e6
        fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True,layout='constrained')
        axes[0].plot(x,vin[mask]);axes[0].set_ylabel('Vin, V')
        axes[1].plot(x,target[mask],'--',label='Target');axes[1].plot(x,out[mask],label='COM');axes[1].legend();axes[1].set_ylabel('HV, V')
        axes[2].plot(x,error[mask]);axes[2].axhline(0,color='black',lw=.5);axes[2].set_ylabel('Error, V')
        axes[3].plot(x,current[mask]);axes[3].set_ylabel('Load current, A');axes[3].set_xlabel(f'Time from {start*1e6:g} us, us')
        for ax in axes:ax.grid(alpha=.3)
        fig.suptitle('OPA810 + VAS / Class B — '+title)
        fig.savefig(HERE/filename,dpi=150);plt.close(fig)
    # Uniform-time RMS; ngspice uses adaptive sampling, so a raw row mean is biased.
    grid=np.linspace(75e-6,102.5e-6,5501)
    e=np.interp(grid,t,error);m=(t>=75e-6)&(t<=102.5e-6)
    report=dict(rows=len(t),stop_s=float(t[-1]),evaluated_cycle=3,time_shift_s=0,
                max_abs_error_v=float(np.max(np.abs(error[m]))),
                rms_error_v=float(np.sqrt(np.trapezoid(e*e,grid)/(grid[-1]-grid[0]))),
                vout_min_v=float(np.min(out[m])),vout_max_v=float(np.max(out[m])),
                peak_abs_load_current_a=float(np.max(np.abs(current[m]))))
    (HERE/'quick_check.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))
    print('Saved waveforms.png, last_pulse.png, waveforms.csv, quick_check.json')

if __name__=='__main__':main()
