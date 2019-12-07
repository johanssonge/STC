# -*- coding: utf-8 -*-
"""
Created on 25 May 2019

Special version of plot1Box to plot the impacts calculated by stat-forw-target
No accumulation is neeed here

Composit version that displays the same chart for all the periods and prints the 
integrated value of the impact in the domain.

@author: Bernard
"""
import gzip, pickle
#import transit as tt
import argparse
import numpy as np
import socket
from datetime import datetime
import matplotlib.pyplot as plt
import os
from collections import OrderedDict

parser = argparse.ArgumentParser()
#parser.add_argument("-y","--year",type=int,help="year")
#parser.add_argument("-m","--month",type=int,choices=1+np.arange(12),help="month")
parser.add_argument("-t","--type",choices=["EAD","EAZ","EIZ-FULL","EID-FULL"],help="type")
parser.add_argument("-st","--stream",type=str,choices=["Jun-01","Jun-11","Jun-21","Jul-01","Jul-11","Jul-21","Aug-01","Aug-11","Aug-21"],help='run_date')
parser.add_argument("-v","--vert",choices=["theta","baro"],help="vertical discretization")
#parser.add_argument("-q","--quiet",type=str,choices=["y","n"],help="quiet (y) or not (n)")
parser.add_argument("-g","--globa",type=str,choices=["y","n"],help="global (y) or not (n)")
parser.add_argument("-hm","--hmax",type=int,choices=[960,1728],help="max age to be considered (hour)")
parser.add_argument("-ht","--hightype",type=str,choices=['mh','vh','sh'],help="high cloud selection")
#parser.add_argument("-a","--all",type=str,choices=["All","Allx","All6","All7","All8"],help="selection of time period")

# default values for the first start day
#year = 2017
#month = 7
#day = 1
supertype = 'EAD'
age_max = 40
water_path = True
quiet = False
vert = 'theta'
# 'FullAMA' or 'global'
target = 'FullAMA'
hightype = 'sh'
nerd = True
water_path = True
#stream = 'Jul-11'
savefig = False

# Choice of what is plotted (these parameters are not passed as arguments yet)
show=True
plot_hist = True
plot_mage = False
plot_mthet = False
plot_mz = False

args = parser.parse_args()
if args.hmax is not None: hmax = args.hmax
if args.type is not None: supertype = args.type
if args.vert is not None: vert = args.vert
#if args.quiet is not None:
#        if args.quiet=='y': quiet=True
#        else: quiet=False
if args.globa is not None:
        if args.globa=='y':target = 'global'
if args.hightype is not None: hightype = args.hightype
if args.stream is not None: stream = args.stream

if socket.gethostname() == 'gort':
    out_dir = "/dkol/data/STC/STC-FORWBox-meanhigh-OUT"
elif 'ciclad' in socket.gethostname():
    out_dir = "/data/legras/STC/STC-FORWBox-meanhigh-OUT"
elif socket.gethostname() == 'Graphium':
    out_dir = "C:\\cygwin64\\home\\berna\\data\\STC\\STC-FORWBox-meanhigh-OUT"
elif socket.gethostname() == 'satie':
    out_dir = "/limbo/data/STC/STC-FORWBox-meanhigh-OUT"
else:
    'This program does not run on this computer'
    exit()
    
if hightype == 'mh':
    suffix = ''
    ht = 'MH'
    suffix2 = '-mh'
elif hightype == 'vh':
    suffix = '_vh'
    ht = 'VH'
    suffix2 = '-vh'
elif hightype == 'sh':
    suffix = '_sh'
    ht = 'SH'
    suffix2 = '-sh'
    
run_type = supertype+'-Box-'+vert+'-'+target

gsum = OrderedDict()
#%%

streams = ['Jul-11','Jul-21','Aug-01','Aug-11','Aug-21']
dates = []

for stream in streams:

    pile_sav_stream  =  os.path.join(out_dir,'pile-save-daily-target-'+run_type+'-'+stream+'-age'+str(24*age_max)+'.pkl')
    with gzip.open(pile_sav_stream,'rb') as f:
        pile = pickle.load(f)
        for date in pile:
            dates.append(date)
            print(date,np.sum(pile[date].transit['hist_t']),np.sum(pile[date].transit['hist_t_sh']),pile[date].count)
            #pile[date].complete()
            gsum[date] = {}
        
        # scaling factor for hist_t and hist_s 
        # 
        # the scaling for hist_t in the volume of each mesh to get an impact density per volume unit in the x,y,theta space
        # this factor is the surface of the mesh used in the target space by which the count must be divided
        # it is further divided by the width of the layer (500m for baro plots and 5K for theta plots) 
        # and multiplied by the interval between outputs, that is 6 h
        # since the mesh is of one degree and that the degree was also the unit used in weighting each pixel in transit
        # we get to use a numerical factor 6/(5*cos(lat_target))
        # the resulting unit is in hour**2 /K for h
        # 
        # We use the same factor for hist_s since the count is made for each layer in the target space
        # but the surface factor is now the surface of the grid in the source space (100 times the satellite image pixel size 
        # but we cancel the cos (lat source factor that was introduced in the scaling of the source))
        # Lsat: we transform units to day**2 by dividing by 576
            ff_t = 6/(5*np.cos(np.radians(pile[date].target['ycent'])))/576
            ff_s = 6/(5*np.cos(np.radians(pile[date].source['ycent'])))/576
            pile[date].transit['hist_s'+suffix] *= ff_s[np.newaxis,:,np.newaxis]
            pile[date].transit['hist_t'+suffix] *= ff_t[np.newaxis,:,np.newaxis]
        
            names = {"EAD":"ERA5 diabatic","EAZ":"ERA5 kinematic",
                 "EIZ":"ERA-I kinematic","EID":"ERA-I diabatic",
                 "EIZ-FULL":"ERA-I kinematic","EID-FULL":"ERA-I diabatic"}
        
            if nerd:
                run_name = run_type+'-'+stream
            else:
                run_name = names[supertype]+' '+target
         
            thet = {3:'340',4:'345',5:'350',6:'355',7:'360',8:'365',9:'370',10:'375',11:'380',13:'390',15:'400',17:'410',19:'420'}
            vmm = {3:1,4:1,5:1,6:1,7:1,8:0.5,9:0.25,10:0.2,11:0.12,13:0.06,15:0.025,17:0.012,19:0.006}
            cosf = np.cos(np.radians(pile[date].target['ycent']))
            degree = 6372 * 2 * np.pi / 360
            area = degree**2    
            for lev in [3,5,6,7,8,9,10,11,13,15,17,19]:
                # update one new layer (deactivate also reset of gsum above)
                #for lev in [4,]: 
                gsum[date][lev] = area*np.sum(pile[date].transit['hist_t_sh'][lev,:,:]*cosf[:,np.newaxis])
                #print(gsum[date][lev])
    #        pile.chart('hist_t'+suffix,lev,txt=run_name+' target '+thet[lev]+' K '+ht+
    #                   ' : conv impact density (day$^2$ K$^{-1}$) '+'sum {:.4g}'.format(gsum[stream][lev]),
    #                   fgp=run_name+'-target-'+thet[lev]+'K'+suffix2,show=show,vmin=0,vmax=vmm[lev])

#%% Plot of gsum for the various levels (420K not shown)
fig=plt.figure(figsize=(6,4))
for lev in [3,5,6,7,8,9,10,11,13,15,17]:
    aa = np.empty(len(dates))
    i = 0
    for date in gsum.keys():
        aa[i] = gsum[date][lev]
        i += 1
    if lev >=6: 
        plt.plot(dates,aa/1000000,lw=4)
    else:
        plt.plot(dates,aa/1000000,'--',lw=4)
plt.legend(('340 K','350 K','355 K','360 K','365 K','370 K','375 K','380 K','390 K','400 K','410 K'),
           loc='best',bbox_to_anchor=(.95,1.05),fontsize=15)
plt.title(r'Cumulated impact per level (10$^6$ day$^2$ km$^2$ K$^{-1})$',fontsize=16)
fig.autofmt_xdate()
plt.tick_params(labelsize=16)
if savefig:
    plt.savefig(os.path.join('figs-Box','cumulated_impact.pdf'),dpi=300,bbox_inches='tight')
    plt.savefig(os.path.join('figs-Box','cumulated_impact.png'),dpi=300,bbox_inches='tight')
plt.show()
#%%

j = 0
fig=plt.figure(figsize=(6,4))
for lev in [3,5,6,7,8,9,10,11,13,15,17]:
    aa = np.empty(len(dates))
    i = 0
    for date in gsum.keys():
        aa[i] = gsum[date][lev]
        i += 1
    aa = aa/aa.max()+0.2*(lev-3)
    if lev >=6: 
        plt.plot(dates,aa,lw=4)
    else:
        plt.plot(dates,aa,'--',lw=4)
    j += 1
date1 = datetime(2017,7,25)
date2 = datetime(2017,8,20)
dd = (date2-date1).days
i1 = 2
i2 = i1 + dd * 1.1 * 0.2/5
plt.plot([date1,date2],[i1,i2],'k')
    
plt.legend(('340 K','350 K','355 K','360 K','365 K','370 K','375 K','380 K','390 K','400 K','410 K'),
           loc='best',bbox_to_anchor=(.95,1.05),fontsize=15)
plt.title('Normalized shifted cumulated impact per level',fontsize=16)
fig.autofmt_xdate()
plt.tick_params(labelsize=16)
if savefig:
    plt.savefig(os.path.join('figs-Box','shifted_cumulated_impact.pdf'),dpi=300,bbox_inches='tight')
    plt.savefig(os.path.join('figs-Box','shifted_cumulated_impact.png'),dpi=300,bbox_inches='tight')
plt.show()
#%%
#pickle.dump(gsum,open('gsum.pkl','wb'))
