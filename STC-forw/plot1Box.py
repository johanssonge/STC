# -*- coding: utf-8 -*-
"""
Created on Fri Nov 11 14:03:50 2016
Modified continuously until 2019

Plots a selection of figures from the transit analysis

Can be used as command with parameters but in practice is run interactively
by changing the parameters in the header

As the transit barotropic diagnostics are of little interest and have not been 
calculated in the recent versions of forward runs, the barotropic section has 
been commented out rather than maintained.

According to the value of the parameter All, the streams are gathered into a group
as indicated in the dictionary date

The choice made by the parameters is
--type: supertype among "EAD","EAZ","EIZ-FULL","EID-FULL"
--vert: "theta" or "baro", in practice ony "theta"
--globa: "global" or "FullAMA", only relevant for the EID-FULL and EIZ-FULL supertypes
--hm: 960 or 1728, max age to be considered
--hightype: cloud type selection among 'mh','vh','sh', in practice use only 'sh'
--all: grouping selection among "All","Allx","All6","All7","All8" (see date dictionary)

Plots which are produced

plot_hist family: impact map in the target space at 340 to 420K levels, impact
map in the source space, same levels, and vertical longitude sections of the impact at 
latitudes 25N, 30N, 35N

Scaling factor for hist_t and hist_s 
 
The scaling for hist_t is calculated in the volume of each mesh to get 
an impact density per volume unit in the x,y,theta space.
This scaling contains the surface of the mesh used in the target space by which 
the count must be divided. It is further divided by the width of the layer 
(500m for baro plots and 5K for theta plots) and multiplied by the interval 
between outputs, that is 6 h (since impact is cumulated over all outputs).
Since the mesh is of one degree and that the degree was also the unit used in 
weighting each pixel in transit we get to use a numerical factor 6/(5*cos(lat_target))
the resulting unit is in hour**2 /K for h. in order to change hours to days, we
further divide by 576.

We use the same factor for hist_s since the count is made for each layer in 
the target space but the surface factor is now the surface of the grid in the 
source space (that is also 1°x1° but multiplied by cos(lat source)). 
The x by cos(lat source) cancels the cos factor introduced in transit.

ff_t = 6/(5*np.cos(np.radians(pile.target['ycent'])))/576
ff_s = 6/(5*np.cos(np.radians(pile.source['ycent'])))/576

plot_mage family: mean age in the target and in the source space, with superimposed 
contours of the impact shown as inverse cumuled proportion, vertical longitude
sections at 25N, 30N, 35N  

plot_mthet family: mean thet of the source in the source space, mean displacement 
in theta in the source space, 

plot_dxy: mean displacement calculated from the source and from the target for
impacts at 340K, 360K, 380K and 400K

The corlormpas are not normalized

@author: Bernard Legras
"""
import gzip, pickle
import transit as tt
import argparse
import numpy as np
import socket
import os

parser = argparse.ArgumentParser()
#parser.add_argument("-y","--year",type=int,help="year")
#parser.add_argument("-m","--month",type=int,choices=1+np.arange(12),help="month")
parser.add_argument("-t","--type",choices=["EAD","EAZ","EIZ-FULL","EID-FULL"],help="type")
parser.add_argument("-v","--vert",choices=["theta","baro"],help="vertical discretization")
#parser.add_argument("-q","--quiet",type=str,choices=["y","n"],help="quiet (y) or not (n)")
parser.add_argument("-g","--globa",type=str,choices=["y","n"],help="global (y) or not (n)")
parser.add_argument("-hm","--hmax",type=int,choices=[960,1728],help="max age to be considered (hour)")
parser.add_argument("-ht","--hightype",type=str,choices=['mh','vh','sh'],help="high cloud selection")
parser.add_argument("-a","--all",type=str,choices=["All","Allx","All6","All7","All8"],help="selection of time period")

# default values for the first start day
#year = 2017
#month = 7
#day = 1
supertype = 'EAD'
hmax = 1728
quiet = False
vert = 'theta' # do not change
# 'FullAMA' or 'global'
target = 'global'
hightype = 'sh'
nerd = True # do not change
water_path = True # does not apply
All = "-All"
# Choice of what is plotted (these parameters are not passed as arguments yet)
show=True
plot_hist = True
plot_mage = False
plot_mthet = False
plot_mz = False # do not change
plt_dxy = False

#here we define temporary values of interactive parameters
# supertype
supertype = 'EID-FULL'
# target
target = "global"
# hmax
hmax = 1728
# plot_hist
# plot_mage
plot_mage = True
# plot_mthet
plot_mthet = True
# plot_dxy
plot_dxy = True

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
if args.all is not None: All = "-"+args.all

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
    
suffix2 = All+'-h'+str(hmax)+suffix2
    
if args.all is not None: All = "-"+args.all

dates ={"-All":["Jun-01","Jun-11","Jun-21","Jul-01","Jul-11","Jul-21","Aug-01","Aug-11","Aug-21"],
        "-Allx":["Jul-11","Jul-21","Aug-01","Aug-11","Aug-21"],
        "-All6":["Jun-01","Jun-11","Jun-21"],
        "-All7":["Jul-01","Jul-11","Jul-21"],
        "-All8":["Aug-01","Aug-11","Aug-21"]}

run_type = supertype+'-Box-'+vert+'-'+target
    
#run_type = supertype+'-N-'+vert+'-'+target
#run_type = supertype+'-Box-'+vert+'-'+target+'-All2-h'+str(hmax)
 
# Definition of the archive as a new transit class
pile = tt.transit(water_path=water_path,vert=vert,target=target)

# Accumulating the data from the multiple runs
for date in dates[All]:
    pile_save_stream = os.path.join(out_dir,'pile-save-stream-'+run_type+'-'+date+'-h'+str(hmax)+'.pkl')
    with gzip.open(pile_save_stream,'rb') as f:
        pile_arch = pickle.load(f)
        print(date,np.sum(pile_arch.transit['hist_t']),np.sum(pile_arch.transit['hist_t_vh']),np.sum(pile_arch.transit['hist_t_sh']))
    pile.merge(pile_arch)
    del pile_arch
print(All,np.sum(pile.transit['hist_t']),np.sum(pile.transit['hist_t_vh']),np.sum(pile.transit['hist_t_sh']))
   
# reading the data
#pile_name = os.path.join(out_dir,'pile-save-stream-'+run_type+'.pkl')
#with gzip.open(pile_name,'rb') as f:  
#    pile = pickle.load(f) 

# making averages
pile.complete()
#print('completion performed')
#pile = tt.transit(water_path = pile2.water_path, vert = pile2.vertype, target = pile2.target['type'])
#pile.transit = pile2.transit

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
ff_t = 6/(5*np.cos(np.radians(pile.target['ycent'])))/576
ff_s = 6/(5*np.cos(np.radians(pile.source['ycent'])))/576
pile.transit['hist_s'+suffix] *= ff_s[np.newaxis,:,np.newaxis]
pile.transit['hist_t'+suffix] *= ff_t[np.newaxis,:,np.newaxis]

names = {"EAD":"ERA5 diabatic","EAZ":"ERA5 kinematic",
         "EIZ":"ERA-I kinematic","EID":"ERA-I diabatic",
         "EIZ-FULL":"ERA-I kinematic","EID-FULL":"ERA-I diabatic"}

if nerd:
    run_name = run_type
else:
    run_name = names[supertype]+' '+target
    
#%%
# deactivated plots as the barotropic perspective does not present any real interest
if vert == 'baro':
    pass
#    if plot_hist:
#        pile.chart('hist_t_vh',0,txt=run_name+' target 10 km VH',fgp=run_type+'-target-10km-vh',show=show)      
#        pile.chart('hist_t_vh',3,txt=run_name+' target 12 km VH',fgp=run_type+'-target-12km-vh',show=show)
#        pile.chart('hist_t_vh',7,txt=run_name+' target 14 km VH',fgp=run_type+'-target-14km-vh',show=show)
#        pile.chart('hist_t_vh',11,txt=run_name+' target 16 km VH',vmin=0,vmax=6,fgp=run_type+'-target-16km-vh',show=show)
#        print(np.sum(pile.transit['hist_t_vh'][11,:,:]),np.sum(pile.transit['hist_s_vh'][11,:,:]))
#        pile.chart('hist_t_vh',15,txt=run_name+' target 18 km VH',fgp=run_type+'-target-18km-vh',show=show)
#        pile.chart('hist_s_vh',0,txt=run_name+' source of 10 km VH',fgp=run_type+'-source-10km-vh',show=show)
#        pile.chart('hist_s_vh',3,txt=run_name+' source of 12 km VH',fgp=run_type+'-source-12km-vh',show=show)
#        pile.chart('hist_s_vh',7,txt=run_name+' source of 14 km VH',fgp=run_type+'-source-14km-vh',show=show)
#        pile.chart('hist_s_vh',11,txt=run_name+' source of 16 km VH',vmin=0,vmax=40,fgp=run_type+'-source-16km-vh',show=show)
#        pile.chart('hist_s_vh',15,txt=run_name+' source of 18 km VH',fgp=run_type+'-source-18km-vh',show=show)
#        pile.chartv('hist_t_vh',30,txt=run_name+' target 30N VH',vmin=0,vmax=2000,fgp=run_type+'-target-30N-vh',show=show)
#        pile.chartv('hist_t_vh',35,txt=run_name+' target 35N VH',vmin=0,vmax=2000,fgp=run_type+'-target-35N-vh',show=show)
#        pile.chartv('hist_t_vh',25,txt=run_name+' target 25N VH',vmin=0,vmax=2000,fgp=run_type+'-target-25N-vh',show=show)
#    if plot_mage:        
#        pile.chartv('mage_t',30,txt=run_name+' mage target 30N',fgp=run_type+'-mage-target-30N',show=show)
#        pile.chartv('mage_t',35,txt=run_name+' mage target 35N',fgp=run_type+'-mage-target-35N',show=show)
#        pile.chartv('mage_t',25,txt=run_name+' mage target 25N',fgp=run_type+'-mage-target-25N',show=show)
#        pile.chart('mage_t',11,txt=run_name+' mage target 16 km',fgp=run_type+'-mage-target-16km',show=show)
#        pile.chart('mage_t',7,txt=run_name+' mage target 14 km',fgp=run_type+'-mage-target-14km',show=show)
#        pile.chart('mage_t',15,txt=run_name+' mage target 18 km',fgp=run_type+'-mage-target-18km',show=show)   
#    if plot_mthet:
#        pile.chart('mthet_s',11,vmin=340,vmax=380,txt=run_name+' mthet source 16 km',fgp=run_type+'-mthet-source-16km',show=show)
#        pile.chart('mthet_s',7,vmin=340,vmax=380,txt=run_name+' mthet source 14 km',fgp=run_type+'-mthet-source-14km',show=show)
#        pile.chart('mthet_s',15,vmin=350,vmax=390,txt=run_name+' mthet source 18 km',fgp=run_type+'-mthet-source-18km',show=show)       
#        pile.chart('mdthet_s',11,txt=run_name+' mdthet source 16 km',fgp=run_type+'-mdthet-source-16km',show=show)
#        pile.chart('mdthet_s',7,txt=run_name+' mdthet source 14 km',fgp=run_type+'-mdthet-source-14km',show=show)
#        pile.chart('mdthet_s',15,txt=run_name+' mdthet source 18 km',fgp=run_type+'-mdthet-source-18km',show=show) 
#    if plot_mz:
#        pile.chart('mz_s',11,vmin=13,vmax=16,txt=run_name+' mz source 16 km',fgp=run_type+'-mz-source-16km',show=show)
#        pile.chart('mz_s',7,vmin=13,vmax=15,txt=run_name+' mz source 14 km',fgp=run_type+'-mz-source-14km',show=show)
#        pile.chart('mz_s',15,vmin=14,vmax=17,txt=run_name+' mz source 18 km',fgp=run_type+'-mz-source-18km',show=show)       
#        pile.chart('mdz_s',11,vmin=0,vmax=3,txt=run_name+' mdz source 16 km',fgp=run_type+'-mdz-source-16km',show=show)
#        pile.chart('mdz_s',7,vmin=-1,vmax=1,txt=run_name+' mdz source 14 km',fgp=run_type+'-mdz-source-14km',show=show)
#        pile.chart('mdz_s',15,vmin=0,vmax=3,txt=run_name+' mdz source 18 km',fgp=run_type+'-mdz-source-18km',show=show) 

#%%
elif vert == 'theta':
    if plot_hist:
        pile.chart('hist_t'+suffix,1,txt=run_name+' target 330 K '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-330K'+suffix2,show=show)
        pile.chart('hist_t'+suffix,3,txt=run_name+' target 340 K '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-340K'+suffix2,show=show)
        pile.chart('hist_t'+suffix,5,txt=run_name+' target 350 K '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-350K'+suffix2,show=show)
        pile.chart('hist_t'+suffix,7,txt=run_name+' target 360 K '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-360K'+suffix2,show=show)
        pile.chart('hist_t'+suffix,9,txt=run_name+' target 370 K '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-370K'+suffix2,show=show)
        pile.chart('hist_t'+suffix,11,txt=run_name+' target 380 K '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-380K'+suffix2,show=show)
        #print('380K',np.sum(pile.transit['hist_t'+suffix][11,:,:]),np.sum(pile.transit['hist_s'+suffix][11,:,:]))
        pile.chart('hist_t'+suffix,13,txt=run_name+' target 390 K '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-390K'+suffix2,show=show)
        pile.chart('hist_t'+suffix,15,txt=run_name+' target 400 K '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-400K'+suffix2,show=show)
        pile.chart('hist_t'+suffix,19,txt=run_name+' target 420 K '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-420K'+suffix2,show=show)    
        pile.chart('hist_s'+suffix,1,txt=run_name+' source of 330 K '+ht+' : conv source density (day$^2$ K$^{-1}$)',fgp=run_type+'-source-330K'+suffix2,show=show)
        pile.chart('hist_s'+suffix,3,txt=run_name+' source of 340 K '+ht+' : conv source density (day$^2$ K$^{-1}$)',fgp=run_type+'-source-340K'+suffix2,show=show)
        pile.chart('hist_s'+suffix,5,txt=run_name+' source of 350 K '+ht+' : conv source density (day$^2$ K$^{-1}$)',fgp=run_type+'-source-350K'+suffix2,show=show)
        pile.chart('hist_s'+suffix,7,txt=run_name+' source of 360 K '+ht+' : conv source density (day$^2$ K$^{-1}$)',fgp=run_type+'-source-360K'+suffix2,show=show)
        pile.chart('hist_s'+suffix,9,txt=run_name+' source of 370 K '+ht+' : conv source density (day$^2$ K$^{-1}$)',fgp=run_type+'-source-370K'+suffix2,show=show)
        pile.chart('hist_s'+suffix,11,txt=run_name+' source of 380 K '+ht+' : conv source density (day$^2$ K$^{-1}$)',fgp=run_type+'-source-380K'+suffix2,show=show)
        pile.chart('hist_s'+suffix,13,txt=run_name+' source of 390 K '+ht+' : conv source density (day$^2$ K$^{-1}$)',fgp=run_type+'-source-390K'+suffix2,show=show)
        pile.chart('hist_s'+suffix,15,txt=run_name+' source of 400 K '+ht+' : conv source density (day$^2$ K$^{-1}$)',fgp=run_type+'-source-400K'+suffix2,show=show)
        pile.chart('hist_s'+suffix,19,txt=run_name+' source of 420 K '+ht+' : conv source density (day$^2$ K$^{-1}$)',fgp=run_type+'-source-420K'+suffix2,show=show)
        pile.chartv('hist_t'+suffix,30,txt=run_name+' target 30N '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-30N'+suffix2,show=show)
        pile.chartv('hist_t'+suffix,35,txt=run_name+' target 35N '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-35N'+suffix2,show=show)
        pile.chartv('hist_t'+suffix,25,txt=run_name+' target 25N '+ht+' : conv impact density (day$^2$ K$^{-1}$)',fgp=run_type+'-target-25N'+suffix2,show=show)   
    #%%
    if plot_mage:
        pile.chartv('mage_t'+suffix,30,txt=run_name+' mean age target 30N '+ht+' (day)',fgp=run_type+'-mage-target-30N'+suffix2,show=show)
        pile.chartv('mage_t'+suffix,35,txt=run_name+' mean age target 35N '+ht+' (day)',fgp=run_type+'-mage-target-35N'+suffix2,show=show)
        pile.chartv('mage_t'+suffix,25,txt=run_name+' mean age target 25N '+ht+' (day)',fgp=run_type+'-mage-target-25N'+suffix2,show=show)
        pile.chart('mage_t'+suffix,1,back_field='hist_t'+suffix,cumsum=True,txt=run_name+' mean age target 330 K '+ht+' (day)',fgp=run_type+'-mage-target-330K'+suffix2,show=show)
        pile.chart('mage_t'+suffix,3,back_field='hist_t'+suffix,cumsum=True,txt=run_name+' mean age target 340 K '+ht+' (day)',fgp=run_type+'-mage-target-340K'+suffix2,show=show)
        pile.chart('mage_t'+suffix,5,back_field='hist_t'+suffix,cumsum=True,txt=run_name+' mean age target 350 K '+ht+' (day)',fgp=run_type+'-mage-target-350K'+suffix2,show=show) 
        pile.chart('mage_t'+suffix,7,back_field='hist_t'+suffix,cumsum=True,txt=run_name+' mean age target 360 K '+ht+' (day)',fgp=run_type+'-mage-target-360K'+suffix2,show=show)
        pile.chart('mage_t'+suffix,9,back_field='hist_t'+suffix,cumsum=True,txt=run_name+' mean age target 370 K '+ht+' (day)',fgp=run_type+'-mage-target-370K'+suffix2,show=show)
        pile.chart('mage_t'+suffix,11,back_field='hist_t'+suffix,cumsum=True,txt=run_name+' mean age target 380 K '+ht+' (day)',fgp=run_type+'-mage-target-380K'+suffix2,show=show)
        pile.chart('mage_t'+suffix,13,back_field='hist_t'+suffix,cumsum=True,txt=run_name+' mean age target 390 K '+ht+' (day)',fgp=run_type+'-mage-target-390K'+suffix2,show=show) 
        pile.chart('mage_t'+suffix,15,back_field='hist_t'+suffix,cumsum=True,txt=run_name+' mean age target 400 K '+ht+' (day)',fgp=run_type+'-mage-target-400K'+suffix2,show=show)
        pile.chart('mage_t'+suffix,19,back_field='hist_t'+suffix,cumsum=True,txt=run_name+' mean age target 420 K '+ht+' (day)',fgp=run_type+'-mage-target-420K'+suffix2,show=show)
    #%%
        pile.chart('mage_s'+suffix,1,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean age source 330 K '+ht+' (day)',fgp=run_type+'-mage-source-330K'+suffix2,show=show)
        pile.chart('mage_s'+suffix,3,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean age source 340 K '+ht+' (day)',fgp=run_type+'-mage-source-340K'+suffix2,show=show)
        pile.chart('mage_s'+suffix,5,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean age source 350 K '+ht+' (day)',fgp=run_type+'-mage-source-350K'+suffix2,show=show) 
        pile.chart('mage_s'+suffix,7,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean age source 360 K '+ht+' (day)',fgp=run_type+'-mage-source-360K'+suffix2,show=show)
        pile.chart('mage_s'+suffix,9,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean age source 370 K '+ht+' (day)',fgp=run_type+'-mage-source-370K'+suffix2,show=show)
        pile.chart('mage_s'+suffix,11,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean age source 380 K '+ht+' (day)',fgp=run_type+'-mage-source-380K'+suffix2,show=show)
        pile.chart('mage_s'+suffix,13,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean age source 390 K '+ht+' (day)',fgp=run_type+'-mage-source-390K'+suffix2,show=show) 
        pile.chart('mage_s'+suffix,15,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean age source 400 K '+ht+' (day)',fgp=run_type+'-mage-source-400K'+suffix2,show=show)
        pile.chart('mage_s'+suffix,19,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean age source 420 K '+ht+' (day)',fgp=run_type+'-mage-source-420K'+suffix2,show=show)
    #%%
    
    #%%
    if plot_mthet: 
        pile.chart('mthet_s'+suffix,3,back_field='hist_s'+suffix,cumsum=True,vmin=330,vmax=360,txt=run_name+' mean PT source of 340 K '+ht+' (K)',fgp=run_type+'-mthet-source-340K'+suffix2,show=show)
        pile.chart('mthet_s'+suffix,7,back_field='hist_s'+suffix,cumsum=True,vmin=355,vmax=365,txt=run_name+' mean PT source of 360 K '+ht+' (K)',fgp=run_type+'-mthet-source-360K'+suffix2,show=show)
        pile.chart('mthet_s'+suffix,11,back_field='hist_s'+suffix,cumsum=True,vmin=355,vmax=375,txt=run_name+' mean PT source of 380 K '+ht+' (K)',fgp=run_type+'-mthet-source-380K'+suffix2,show=show)
        pile.chart('mthet_s'+suffix,15,back_field='hist_s'+suffix,cumsum=True,vmin=360,vmax=380,txt=run_name+' mean PT source of 400 K '+ht+' (K)',fgp=run_type+'-mthet-source-400K'+suffix2,show=show)
        pile.chart('mdthet_s'+suffix,3,back_field='hist_s'+suffix,cumsum=True,vmin=-25,vmax=10,txt=run_name+' mean dPT source of 340 K '+ht+' (K)',fgp=run_type+'-mdthet-source-340K'+suffix2,show=show)
        pile.chart('mdthet_s'+suffix,7,back_field='hist_s'+suffix,cumsum=True,vmin=-5,vmax=10,txt=run_name+' mean dPT source of 360 K '+ht+' (K)',fgp=run_type+'-mdthet-source-360K'+suffix2,show=show)
        pile.chart('mdthet_s'+suffix,11,back_field='hist_s'+suffix,cumsum=True,vmin=5,vmax=20,txt=run_name+' mean dPT source of 380 K '+ht+' (K)',fgp=run_type+'-mdthet-source-380K'+suffix2,show=show)
        pile.chart('mdthet_s'+suffix,15,back_field='hist_s'+suffix,cumsum=True,vmin=10,vmax=40,txt=run_name+' mean dPT source of 400 K '+ht+' (K)',fgp=run_type+'-mdthet-source-400K'+suffix2,show=show)
        #%%
        pile.chart('mdthet_t'+suffix,7,back_field='hist_t'+suffix,cumsum=True,vmin=-15,vmax=5,txt=run_name+' mean dPT target 340 K '+ht+' (K)',fgp=run_type+'-mdthet-target-360K'+suffix2,show=show)  
        pile.chart('mdthet_t'+suffix,7,back_field='hist_t'+suffix,cumsum=True,vmin=-1,vmax=2,txt=run_name+' mean dPT target 360 K '+ht+' (K)',fgp=run_type+'-mdthet-target-360K'+suffix2,show=show)  
        pile.chart('mdthet_t'+suffix,11,back_field='hist_t'+suffix,cumsum=True,vmin=12,vmax=15,txt=run_name+' mean dPT target 380 K '+ht+' (K)',fgp=run_type+'-mdthet-target-380K'+suffix2,show=show) 
        pile.chart('mdthet_t'+suffix,15,back_field='hist_t'+suffix,cumsum=True,vmin=25,vmax=35,txt=run_name+' mean dPT target 400 K '+ht+' (K)',fgp=run_type+'-mdthet-target-400K'+suffix2,show=show)
    #%%
#    if plot_mz:
#        pile.chart('mz_s'+suffix,7,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean z source 360 K '+ht+' (km)',fgp=run_type+'-mz-source-360K'+suffix2,show=show)
#        pile.chart('mz_s'+suffix,11,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean z source 380 K '+ht+' (km)',fgp=run_type+'-mz-source-380K'+suffix2,show=show)
#        pile.chart('mz_s'+suffix,15,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean z source 400 K '+ht+' (km)',fgp=run_type+'-mz-source-400K'+suffix2,show=show)
#        pile.chart('mdz_s'+suffix,7,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean dz source 360 K '+ht+' (km)',fgp=run_type+'-mdz-source-360K'+suffix2,show=show)
#        pile.chart('mdz_s'+suffix,11,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean dz source 380 K '+ht+' (km)',fgp=run_type+'-mdz-source-380K'+suffix2,show=show)
#        pile.chart('mdz_s'+suffix,15,back_field='hist_s'+suffix,cumsum=True,txt=run_name+' mean dz source 400 K '+ht+' (km)',fgp=run_type+'-mdz-source-400K'+suffix2,show=show)
    #%%
    if plot_dxy:
        pile.vect(3,type='source',thresh=0.0005,txt=run_name+' mean source displacement 340 K '+ht+' (K)',fgp=run_type+'-displace-target-340K'+suffix2,show=show)
        pile.vect(3,type='target inv',thresh=0.0002,txt=run_name+' mean target displacement 340 K '+ht+' (K)',fgp=run_type+'-displace-source-340K'+suffix2,show=show)
        pile.vect(7,type='source',thresh=0.0005,txt=run_name+' mean source displacement 360 K '+ht+' (K)',fgp=run_type+'-displace-target-360K'+suffix2,show=show)
        pile.vect(7,type='target inv',thresh=0.0002,txt=run_name+' mean target displacement 360 K '+ht+' (K)',fgp=run_type+'-displace-source-360K'+suffix2,show=show)
        pile.vect(11,type='source',thresh=0.0005,txt=run_name+' mean source displacement 380 K '+ht+' (K)',fgp=run_type+'-displace-target-380K'+suffix2,show=show)
        pile.vect(11,type='target inv',thresh=0.0002,txt=run_name+' mean target displacement 380 K '+ht+' (K)',fgp=run_type+'-displace-source-380K'+suffix2,show=show)
        pile.vect(15,type='source',thresh=0.0005,txt=run_name+' mean source displacement 400 K '+ht+' (K)',fgp=run_type+'-displace-target-400K'+suffix2,show=show)
        pile.vect(15,type='target inv',thresh=0.0002,txt=run_name+' mean target displacement 400 K '+ht+' (K)',fgp=run_type+'-displace-source-400K'+suffix2,show=show)