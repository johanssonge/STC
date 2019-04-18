#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Opens a FLEXPART type grib file from ECMWF and reads meteorological fields.
Requires pygrib, loaded from conda-forge
For both python 2 and python 3 under anaconda
ACHTUNG: in some installations of python 3, error at loading stage because
of libZ not found. Remedy: load netCDF4 in the calling program even if not used.

Functions: Open files, read the data, extract subgrids, make charts, interpolate in time, 
interpolate to pressure levels

Data are read on hybrid levels. They can interpolated to pressure levels. Do it on subgrids
as it is a time consuming procedure.

Usage:
>> from ECMWF_N import ECMWF
open files for a date (datetime) and a project (VOLC or STC)
>> data = ECMWF(project,date)
read a variable var
>> data._get_var(var)
example: data._get_var('CC') for cloud cover (see lists in ECMWF class)
calculate pressure field
>> data._mkp()
calculate potential temperature (requires to read T and calculate P before)
>> data._mktheta()
extract a subgrid
>> data1 = data.extract(latRange=[lat1,lat2],lonRange=[lon1,lon2])
plot a chart for the variable var and level lev (lev is the level number)
>> data.chart(var,lev)
interpolate in time (date2 must be between the dates of data0 and data1)
>> data2 = data0.interpol-time(data1,date2)
interpolate to pressure levels
>> data1 = data.interpolP(pList,varList,latRange,lonRange)
where pList is a pressure or a list of pressures, varList is a variable or a list of variables, 
latRange and lonRange as in extract
    
The ECMWF class is used to read the file corresponding to a date for several projects/
The relevant projects are STC and VOLC
  
The ECMWF_pure allows to define a template object without reading files.
It can be used to modify data. It is produced as an output of the interpolation.

Created on 21/01/2018 from ECMWF.py

@author: Bernard Legras (legras@lmd.ens.fr)
@licence: CeCILL-C
"""
from __future__ import division, print_function
#from __future__ import unicode_literals
from datetime import datetime
import numpy as np
import math
import pygrib
import os
#from mpl_toolkits.basemap import Basemap
from cartopy import feature
#from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import socket
from scipy.interpolate import RegularGridInterpolator
from mki2d import tohyb
import constants as cst
import gzip,pickle
from numba import jit

MISSING = -999
# Physical constants
# now in the package "constants"
#R = 287.04 # or 287.053
#Cpd = 1005.7
#kappa = R/Cpd
#g = 9.80665
#pref = 101325.
#p0 = 100000.

def strictly_increasing(L):
    return all(x<y for x, y in zip(L, L[1:]))

# Second order estimate of the first derivative dy/dx for non uniform spacing of x  
d = lambda x,y:(1/(x[2:,:,:]-x[:-2,:,:]))\
                *((y[2:,:,:]-y[1:-1,:,:])*(x[1:-1,:,:]-x[:-2,:,:])/(x[2:,:,:]-x[1:-1,:,:])\
                -(y[:-2,:,:]-y[1:-1,:,:])*(x[2:,:,:]-x[1:-1,:,:])/(x[1:-1,:,:]-x[:-2,:,:]))

# template object produced by extraction and interpolation
class ECMWF_pure(object):
    def __init__(self):
        self.var={}
        self.attr={}
        self.d2d={}
        self.warning = []

    def show(self,var,lev=0,txt=None,log=False):
        """ Chart for data fields """
        # test existence of key field
        if var in self.var.keys():
            if len(self.var[var].shape) == 3:
                buf = self.var[var][lev,:,:]
            else:
                buf = self.var['var']
        elif var in self.d2d.keys():
            buf = self.d2d[var]
        else:
            print ('undefined field')
            return
        fs=15
        # it is unclear how the trick with cm_lon works in imshow but it does
        # the web says that it is tricky to plot data accross dateline with cartopy
        # check https://stackoverflow.com/questions/47335851/issue-w-image-crossing-dateline-in-imshow-cartopy
        cm_lon =0
        # guess that we want to plot accross dateline 
        if self.attr['lons'][-1] > 180: cm_lon=180
        proj = ccrs.PlateCarree(central_longitude=cm_lon)
        fig = plt.figure(figsize=[11,4])
        fig.subplots_adjust(hspace=0,wspace=0.5,top=0.925,left=0.)
        ax = plt.axes(projection = proj)
        iax = ax.imshow(buf, transform=proj, interpolation='nearest',
                    extent=[self.attr['lons'][0]-cm_lon, self.attr['lons'][-1]-cm_lon,
                            self.attr['lats'][0], self.attr['lats'][-1]],
                    origin='lower', aspect=1.,cmap='jet')
        ax.add_feature(feature.NaturalEarthFeature(
            category='cultural',
            name='admin_1_states_provinces_lines',
            scale='50m',
            facecolor='none'))
        ax.coastlines('50m')
        #ax.add_feature(feature.BORDERS)
        # The grid adjusts automatically with the following lines
        # If crossing the dateline, superimposition of labels there
        # can be suppressed by specifying xlocs
        xlocs = None
        if cm_lon == 180: xlocs = [0,60,120,180,-120,-60]
        gl = ax.gridlines(draw_labels=True, xlocs=xlocs,
                      linewidth=2, color='gray', alpha=0.5, linestyle='--')
        gl.xlabels_top = False
        gl.ylabels_right = False
        #gl.xformatter = LONGITUDE_FORMATTER
        #gl.yformatter = LATITUDE_FORMATTER
        gl.xlabel_style = {'size': fs}
        gl.ylabel_style = {'size': fs}
        #gl.xlabel_style = {'color': 'red', 'weight': 'bold'}
        
        if txt is None:
            plt.title(var,fontsize=fs)
        else:
            plt.title(txt,fontsize=fs)
        # plot adjusted colorbar
        axpos = ax.get_position()
        pos_x = axpos.x0 + axpos.x0 + axpos.width + 0.01
        pos_cax = fig.add_axes([pos_x,axpos.y0,0.04,axpos.height])
        cbar=fig.colorbar(iax,cax=pos_cax)
        cbar.ax.tick_params(labelsize=fs)

        plt.show()
        return None

    def extract(self,latRange=None,lonRange=None,varss=None,vard=None):
        """ extract all variables on a reduced grid
           varss is a list of the 3D variables
           vard is a list of the 2D variables 
        """
        # first determine the boundaries of the domain
        new = ECMWF_pure()
        if (latRange == []) | (latRange == None):
            new.attr['lats'] = self.attr['lats']
            nlatmin = 0
            nlatmax = len(self.attr['lats'])
        else:
            nlatmin = np.abs(self.attr['lats']-latRange[0]).argmin()
            nlatmax = np.abs(self.attr['lats']-latRange[1]).argmin()+1
        if (lonRange == []) | (lonRange == None):
            new.attr['lons'] = self.attr['lons']
            nlonmin = 0
            nlonmax = len(self.attr['lons'])
        else:
            nlonmin = np.abs(self.attr['lons']-lonRange[0]).argmin()
            nlonmax = np.abs(self.attr['lons']-lonRange[1]).argmin()+1
        new.attr['lats'] = self.attr['lats'][nlatmin:nlatmax]
        new.attr['lons'] = self.attr['lons'][nlonmin:nlonmax]
        new.nlat = len(new.attr['lats'])
        new.nlon = len(new.attr['lons'])
        new.nlev = self.nlev
        new.attr['levtype'] = self.attr['levtype']
        new.date = self.date
        new.attr['La1'] = self.attr['lats'][nlatmin]
        new.attr['Lo1'] = self.attr['lons'][nlonmin]
        new.attr['dla'] = self.attr['dla']
        new.attr['dlo'] = self.attr['dlo']
        # extraction
        if varss is None:
            list_vars = []
        elif varss == 'All':
            list_vars = self.var.keys()
        else:
            list_vars = varss
        for var in list_vars:
            if len(self.var[var].shape) == 3:
                new.var[var] = self.var[var][:,nlatmin:nlatmax,nlonmin:nlonmax]
            else:
                new.var[var] = self.var[var][nlatmin:nlatmax,nlonmin:nlonmax]
        if vard is None:
            list_vars = []
        elif vard == 'All':
            list_vars = self.d2d.keys()
        else:
            list_vars = vard
        for var in list_vars:
            new.d2d[var] = self.d2d[var][nlatmin:nlatmax,nlonmin:nlonmax]
        return new
    
    def zonal(self,vars=None,vard=None):
        """ Calculate the zonal averages of the variables contained in self"""
        new = ECMWF_pure()
        new.attr['lats'] = self.attr['lats']
        new.nlat = len(new.attr['lats'])
        new.nlev = self.nlev
        if vars is None:
            list_vars = []
        elif vars == 'All':
            list_vars = self.var.keys()
        else:
            list_vars = vars
        for var in list_vars:
            lx = len(self.var[var].shape)-1
            new.var[var] = np.mean(self.var[var],axis=lx)
        if vard is None:
            list_vars = []
        elif vard == 'All':
            list_vars = self.d2d.keys()
        else:
            list_vars = vard
        for var in list_vars:
            new.d2d[var] = np.mean(self.d2d[var],axis=1)
        return new    
    
    def getxy(self,var,lev,y,x):
        """ get the interpolated value of var in x, y on the level lev """
        # Quick n' Dirty version by nearest neighbour
        jy = np.abs(self.attr['lats']-y).argmin()
        ix = np.abs(self.attr['lons']-x).argmin()
        return self.var[var][lev,jy,ix]       

    def interpol_time(self,other,date):
        # This code interpolate in time between two ECMWF objects with same vars
        # check the date
        if self.date < other.date:
            if (date > other.date) | (date < self.date):
                print ('error on date')
                print (self.date,date,other.date)
                return -1
        else:
            if (date < other.date) | (date > self.date):
                print ('error on date')
                print (other.date,date,self.date)
                return -1
        # calculate coefficients
        dt = (other.date-self.date).total_seconds()
        dt1 = (date-self.date).total_seconds()
        dt2 = (other.date-date).total_seconds()
        cf1 = dt2/dt
        cf2 = dt1/dt
        #print ('cf ',cf1,cf2)
        data = ECMWF_pure()
        data.date = date
        for names in ['lons','lats']:
            data.attr[names] = self.attr[names]
        data.nlon = self.nlon
        data.nlat = self.nlat
        data.nlev = self.nlev
        for var in self.var.keys():
            data.var[var] = cf1*self.var[var] + cf2*other.var[var]
        try:
            for var in self.d2d.keys():
               data.d2d[var] = cf1*self.d2d[var] + cf2*other.d2d[var]
        except:
            pass
        return data
    
    def interpolP(self,p,varList='All',latRange=None,lonRange=None):
        """ interpolate the variables to a pressure level or a set of pressure levels
            vars must be a list of variables or a single varibale
            p must be a list of pressures in Pascal
        """
        if 'P' not in self.var.keys():
            self._mkp()
        new = ECMWF_pure()
        if varList == 'All':
            varList = list(self.var.keys())
            varList.remove('SP')
            varList.remove('P')
        elif type(varList) == str:
            varList = [varList,]
        for var in varList:
            if var not in self.var.keys():
                print(var,' not defined')
                return
        if type(p) != list:
            p = [p,]
        if 'P' not in self.var.keys():
            print('P not defined')
            return
        # first determine the boundaries of the domain
        if (latRange == []) | (latRange == None):
            nlatmin = 0
            nlatmax = self.nlat
        else:
            nlatmin = np.abs(self.attr['lats']-latRange[0]).argmin()
            nlatmax = np.abs(self.attr['lats']-latRange[1]).argmin()+1
        if (lonRange == []) | (lonRange == None):
            nlonmin = 0
            nlonmax = self.nlon
        else:
            nlonmin = np.abs(self.attr['lons']-lonRange[0]).argmin()
            nlonmax = np.abs(self.attr['lons']-lonRange[1]).argmin()+1
        new.attr['lats'] = self.attr['lats'][nlatmin:nlatmax]
        new.attr['lons'] = self.attr['lons'][nlonmin:nlonmax]
        new.nlat = len(new.attr['lats'])
        new.nlon = len(new.attr['lons'])
        new.date = self.date
        new.nlev = len(p)
        new.attr['levtype'] = 'pressure'
        new.attr['plev'] = p
        pmin = np.min(p)
        pmax = np.max(p)
        for var in varList:
            new.var[var] = np.empty(shape=(len(p),nlatmax-nlatmin,nlonmax-nlonmin))
            jyt = 0
            # big loop that should be paralellized or calling numa for good performance
            for jys in range(nlatmin,nlatmax):
                ixt = 0
                for ixs in range(nlonmin,nlonmax):
                    # find the range of p in the column
                    npmin = np.abs(self.var['P'][:,jys,ixs]-pmin).argmin()
                    npmax = np.abs(self.var['P'][:,jys,ixs]-pmax).argmin()+1
                    npmin = max(npmin - 3,0)
                    npmax = min(npmax + 3,self.nlev)
                    # Better version than the linear interpolation but much too slow
                    #fint = PchipInterpolator(np.log(self.var['P'][npmin:npmax,jys,ixs]),
                    #                     self.var[var][npmin:npmax,jys,ixs])
                    #new.var[var][:,jyt,ixt] = fint(np.log(p))
                    new.var[var][:,jyt,ixt] = np.interp(np.log(p),np.log(self.var['P'][npmin:npmax,jys,ixs]),self.var[var][npmin:npmax,jys,ixs])
                    ixt += 1
                jyt += 1
        return new

    def interpol_part(self,p,x,y,varList='All'):
        """ Interpolate the variables to the location of particles given by [p,y,x] using trilinear method."""  
        if 'P' not in self.var.keys():
            self._mkp()
        if varList == 'All':
            varList = list(self.var.keys())
            varList.remove('SP')
            varList.remove('P')
        elif type(varList) == str:
            varList = [varList,]
        for var in varList:
            if var not in self.var.keys():
                print(var,' not defined')
                return
        # Defines output dictionary 
        result = {}
        # test whether fhyb already attached to the instance
        if not hasattr(self,'fhyb'):
            self.fhyb,void = tohyb()
        # generate the 2D interpolator of the surface pressure
        lsp = RegularGridInterpolator((self.attr['lats'],self.attr['lons']),-np.log(self.var['SP']))
        lspi = lsp(np.transpose([y,x]))
        # define -log sigma = -log(p) - -log(ps)
        lsig = - np.log(p) - lspi
        # find the non integer hybrib level with offset due to the truncation of levels
        hyb = self.fhyb(np.transpose([lsig,lspi]))-self.attr['levs'][0]+1
        lhyb = np.floor(hyb).astype(np.int64)
        # flag non valid parcels outside the domain (see discussion in convsrc2)
        # notive that hyb == 100 not flagged as invalid, but clipped below
        non_valid = np.where(hyb>100)[0]
        # clip lhyb to remove out of bounds problems due to non valid parcels
        lhyb = np.clip(lhyb,0,99)
        #@@ test the extreme values of sigma end ps
        if np.min(lsig) < - np.log(0.95):
            print('large sigma detected ',np.exp(-np.min(lsig)))
        if np.max(lspi) > -np.log(45000):
            print('small ps detected ',np.exp(-np.max(lspi)))
        # Horizontal interpolation
        # clipping to avoid boundary effects for parcels just on the edges (especially on the eastern edge)
        ix = np.clip(np.floor((x-self.attr['Lo1'])/self.attr['dlo']).astype(np.int64),0,self.nlon-2)
        jy = np.clip(np.floor((y-self.attr['La1'])/self.attr['dla']).astype(np.int64),0,self.nlat-2)
        px = ((x - self.attr['Lo1']) %  self.attr['dlo'])/self.attr['dlo']
        py = ((y - self.attr['La1']) %  self.attr['dla'])/self.attr['dla']
        for var in varList:
            vhigh = (1-px)*(1-py)*self.var[var][lhyb,jy,ix] + (1-px)*py*self.var[var][lhyb,jy+1,ix] \
                  + px*(1-py)*self.var[var][lhyb,jy,ix+1] + px*py*self.var[var][lhyb,jy+1,ix+1]
            vlow  = (1-px)*(1-py)*self.var[var][lhyb+1,jy,ix] + (1-px)*py*self.var[var][lhyb+1,jy+1,ix] \
                  + px*(1-py)*self.var[var][lhyb+1,jy,ix+1] + px*py*self.var[var][lhyb+1,jy+1,ix+1]
            hc = hyb - lhyb
            result[var] = (1-hc)*vhigh + hc*vlow
            result[var][non_valid] = MISSING
        return result  
           
    def _CPT(self):
        """ Calculate the cold point tropopause """
        if not set(['T','P']).issubset(self.var.keys()):
            print('T or P undefined')
            return
        levbnd = {'FULL-EA':[30,90],'FULL-EI':[15,43]}
        # TODO: find a way to avoid the big loop
        self.d2d['pcold'] = np.empty(shape=(self.nlat,self.nlon))
        self.d2d['Tcold'] = np.empty(shape=(self.nlat,self.nlon))
        if 'Z' in self.var.keys():
            self.d2d['zcold'] = np.empty(shape=(self.nlat,self.nlon))
        # Calculate the cold point in the discrete profile
        # TO DO: make a smoother version with vertical interpolation
        nc = np.argmin(self.var['T'][levbnd[self.project][0]:levbnd[self.project][1],...],axis=0)\
           + levbnd[self.project][0]
        for jy in range(self.nlat):
            for ix in range(self.nlon):
                self.d2d['pcold'][jy,ix] = self.var['P'][nc[jy,ix],jy,ix]
                self.d2d['Tcold'][jy,ix] = self.var['T'][nc[jy,ix],jy,ix]
        if  'Z' in self.var.keys():
            for jy in range(self.nlat):
                for ix in range(self.nlon):
                    self.d2d['zcold'][jy,ix] = self.var['Z'][nc[jy,ix],jy,ix]
        return
    
    def _lzrh(self):
        """ Calculate the clear sky and all sky lzrh. Translated from LzrnN.m 
        Not yet validated. Use with cautione.
        """
        if not set(['P','ASSWR','ASLWR','CSSWR']).issubset(self.var.keys()):
            print('P or heating rate missing')
            return
        # Restrict the column (top at 60 hPa) 
        ntop1 = 60 - self.attr['levs'][0]
        nbot1 = self.attr['levs'][-1] - 30
        self.d2d['plzrh'] = np.ma.empty(shape=(self.nlat,self.nlon))
        self.d2d['ptlzrh'] = np.ma.empty(shape=(self.nlat,self.nlon))
        self.d2d['aslzrh'] = np.ma.empty(shape=(self.nlat,self.nlon))
        uniq = np.empty(shape=(self.nlat,self.nlon))
        for jy in range(self.nlat):
            for ix in range(self.nlon):
                print(jy,ix)
                # Clear sky heating in the column
                csh = self.var['CSSWR'][ntop1:nbot1,jy,ix] + self.var['CSLWR'][ntop1:nbot1,jy,ix]
                # Define location of positive heating
                lp = (csh>0).astype(np.int64)
                # Find position of vertical crossings of zero heating
                pos = np.where(lp[1:]-lp[:-1]==-1)[0]
                # Number of crossings
                uniq[jy,ix] = len(pos)
                # Select column with at least one crossing and make sure there is heating 
                # in the strato below 66 hpa level to eliminate tropopause folds in the subtropics
                if len(pos)==0 | np.max(cst[:11]<0):
                    self.d2d['plzrh'][jy,ix] = np.ma.masked
                    self.d2d['ptlzrh'][jy,ix] = np.ma.masked
                    self.d2d['aslzrh'][jy,ix] = np.ma.masked
                    continue
                # Calculate pressure at each crossing
                pzk = []
                px = []
                for k in range(len(pos)):
                    id = pos[k]
                    #@@ Temporary test
                    if (cst[id]*csh[id+1]>0) | (csh[id]<0):
                        print('ERROR: localization')
                        return
                    px.append(csh[id]/(csh[id]-csh[id+1]))
                    # Interopolate to get intersection
                    pzk.append(math.exp(px[k]*math.log(self.var['P'][id+1,jy,ix])+(1-px[k])*math.log(self.var['P'][id,jy,ix])))
                # Now we test the best continuity for pressure
                # Collect neighbour values of the LZRH pressure already calculated
                # and find intersections in the current column which is closest to these values
                
                if len(pos)==1: 
                    k=1
                else:
                    if jy>0 & ix>0:
                        if ix<self.nlon-1:
                            pzt = list(self.d2d['plzrh'][jy-1,ix-1:ix+2])
                            pzt.append(self.d2d['plzrh'][jy,ix-1])
                        else:
                            pzt = list(self.d2d['plzrh'][jy-1,ix-1:ix+1])
                            pzt.append(self.d2d['plzrh'][jy,ix-1])
                    elif jy==0 & ix>0:
                        pzt = [self.d2d['plzrh'][jy,ix-1],]
                    elif jy>0 & ix==0:
                        pzt = list(self.d2d['plzrh'][jy-1,ix:ix+2])
                    else:              
                        pzt = []
                    if len(pzt)>0:
                        avpzt = sum(pzt)/len(pzt)
                        k = np.argmin((np.array(pzk)-avpzt)**2)
                        # This patch corrects some rare artefacts near the tropopause
                        # (empirical)
                        if pzk[k] < 9500:
                            print(jy,ix,len(pzk),avpzt,len(pzt),pzt,type(pzt))
                            idx = np.sort((np.array(pzk)-avpzt)**2)
                            if pzk[idx[0]]>12000:
                                k=idx[0]
                    else:
                        k=1
                self.d2d['plzrh'][jy,ix] = pzk[k]
                # test
                if jy==166 & ix==0:
                    print(k,pzk[k])
                # Calculate potential temperature and all sky heating at the LZRH
                tz = px[k]*self.var['T'][pos[k]+1,jy,ix] + (1-px[k])*self.var['T'][pos[k],jy,ix]
                self.d2d['ptlzrh'][jy,ix] = tz * (cst.p0/pzk[k])**cst.kappa
                self.d2d['aslzrh'][jy,ix] = px[k]*self.var['ASSWR'][pos[k]+1,jy,ix] + (1-px[k])*self.var['ASSWR'][pos[k],jy,ix] \
                                          + px[k]*self.var['ASLWR'][pos[k]+1,jy,ix] + (1-px[k])*self.var['ASLWR'][pos[k],jy,ix]
        return            
    
    @jit
    def _WMO(self,highlatOffset=False):
        """ Calculate the WMO tropopause 
        When highlatoffset is true the 2K/km criterion is replaced by a 3K/km 
        at high latitudes latitudes above 60S or 60N """
        if not set(['T','P']).issubset(self.var.keys()):
            print('T or P undefined')
            return
        self.d2d['pwmo'] = np.ma.empty(shape=(self.nlat,self.nlon))
        self.d2d['Twmo'] = np.ma.empty(shape=(self.nlat,self.nlon))
        if 'Z' in self.var.keys():
            self.d2d['zwmo'] = np.empty(shape=(self.nlat,self.nlon))
            zwmo = True
        else:
            zwmo = False
        levbnd = {'FULL-EA':[30,90],'FULL-EI':[15,43]}
        highbnd = levbnd[self.project][0]
        lowbnd =  levbnd[self.project][1]
        logp = np.log(self.var['P'])
        # dz from the hydrostatic formula dp/dz = - rho g = - p/T g /R 
        # dz = dz/dp p dlogp = - 1/T R/g dlogp (units m)
        # dz is shifted b one index position / T, p
        # dz[i] is the positive logp thickness for the layer between levels i and i+1, that is 
        # above level i+1
        dz = cst.R/cst.g * self.var['T'][1:,:,:] * (logp[1:,:,:]-logp[:-1,:,:])
        # calculate dT/dz = - 1/p dT/dlogp rho g = - g/R 1/T dT/dlogp 
        # dTdz[i] is the vertical derivative at level [i+1]
        #lapse = - cst.g/cst.R * (1/self.var['T'][highbnd+1:lowbnd-1,...]) * \
        #               (self.var['T'][highbnd:lowbnd-2,...] - self.var['T'][highbnd+2:lowbnd,...]) / \
        #               (logp[highbnd:lowbnd-2,...]-logp[highbnd+2:lowbnd,...])
        lapse = - cst.g/cst.R * (1/self.var['T'][highbnd+1:lowbnd,...]) * \
                       (self.var['T'][highbnd:lowbnd-1,...] - self.var['T'][highbnd+1:lowbnd,...]) / \
                       (logp[highbnd:lowbnd-1,...]-logp[highbnd+1:lowbnd,...])
        
        for jy in range(self.nlat):                       
            # standard wmo criterion
            offset = - 0.002
            thicktrop = 2000
            # adaptation of the WMO offset at high latitude
            if highlatOffset & (abs(self.attr['lats'][jy]) > 60): offset = -0.003
            for ix in range(self.nlon):
                # location of lapse rate exceeding the threshod 
                slope = list(np.where(lapse[:,jy,ix] > offset)[0])
                Deltaz = 0.
                found = False
                # explore slope to find the first case where the slope is maintained
                # over two km
                # This is required to avoid shallow inversion layers to be confused with
                # the tropopause
                while not found:
                    if len(slope)>0: # should be done with try but forbidden with numba
                        # candidate tropopause
                        test = slope.pop()
                    else:
                        # if all slopes have been processed without finding a suitable tropopause, mask loc
                        self.d2d['pwmo'][jy,ix] = np.ma.masked
                        self.d2d['Twmo'][jy,ix] = np.ma.masked
                        if zwmo: self.d2d['zwmo'][jy,ix] = np.ma.masked
                        found = True
                        break
                    # location of the basis of the interval 
                    # +1 to account for the shift of the finite difference
                    lev0 = test+1+highbnd
                    lev = lev0-1
                    Deltaz = dz[lev,jy,ix]
                    # performs search above the candidate tropopause
                    search = True
                    while Deltaz < thicktrop:
                        lev -= 1
                        Deltaz += dz[lev,jy,ix]
                        # mean slope over the considered layer
                        if (self.var['T'][lev,jy,ix]-self.var['T'][lev0,jy,ix])/Deltaz < offset: 
                            search = False
                            break
                    if search: 
                        found = True
                        self.d2d['pwmo'][jy,ix] = self.var['P'][lev0,jy,ix]
                        self.d2d['Twmo'][jy,ix] = self.var['T'][lev0,jy,ix]
                        if zwmo: self.d2d['zwmo'][jy,ix] = self.var['Z'][lev0,jy,ix]      
        return 
       
    def interpol_track(self,p,x,y,varList='All'):
        """ Calculate the distance to the cold point and to the LZRH ."""  
        if 'P' not in self.var.keys():
            self._mkp()
        if varList == 'All':
            varList = list(self.var.keys())
            varList.remove('SP')
            varList.remove('P')
        elif type(varList) == str:
            varList = [varList,]
        for var in varList:
            if var not in self.var.keys():
                print(var,' not defined')
                return
        # Defines output dictionary 
        result = {}
        # test whether fhyb already attached to the instance
        if not hasattr(self,'fhyb'):
            self.fhyb,void = tohyb()
        # generate the 2D interpolator of the surface pressure
        lsp = RegularGridInterpolator((self.attr['lats'],self.attr['lons']),-np.log(self.var['SP']))
        lspi = lsp(np.transpose([y,x]))
        # define -log sigma = -log(p) - -log(ps)
        lsig = - np.log(p) - lspi
        # find the non integer hybrib level
        hyb = self.fhyb(np.transpose([lsig,lspi]))-self.attr['levs'][0]+1
        lhyb = np.floor(hyb).astype(np.int64)
        #@@ test the extreme values of sigma end ps
        if np.min(lsig) < - np.log(0.95):
            print('large sigma detected ',np.exp(-np.min(lsig)))
        if np.max(lspi) > -np.log(45000):
            print('small ps detected ',np.exp(-np.max(lspi)))
        # Horizontal interpolation
        ix = np.floor((x-self.attr['Lo1'])/self.attr['dlo']).astype(np.int64)
        jy = np.floor((y-self.attr['la1'])/self.attr['dla']).astype(np.int64)
        px = ((x - self.attr['Lo1']) %  self.attr['dlo'])/self.attr['dlo']
        py = ((y - self.attr['La1']) %  self.attr['dla'])/self.attr['dla']
        for var in varList:
            vhigh = (1-px)*(1-py)*self.var[var][lhyb,jy,ix] + (1-px)*py*self.var[var][lhyb,jy+1,ix] \
                  + px*(1-py)*self.var[var][lhyb,jy,ix+1] + px*py*self.var[var][lhyb,jy+1,ix+1]
            vlow  = (1-px)*(1-py)*self.var[var][lhyb+1,jy,ix] + (1-px)*py*self.var[var][lhyb+1,jy+1,ix] \
                  + px*(1-py)*self.var[var][lhyb+1,jy,ix+1] + px*py*self.var[var][lhyb+1,jy+1,ix+1]
            hc = hyb % 1
            result[var] = (1-hc)*vhigh + hc*vlow
            del hc; del vhigh; del vlow
        return result  
                        
# standard class to read data
class ECMWF(ECMWF_pure):
    # to do: raise exception in case of an error
    
    def __init__(self,project,date):
        ECMWF_pure.__init__(self)
        self.project = project
        self.date = date
        #SP_expected = False
        self.EN_expected = False
        self.DI_expected = False
        self.WT_expected = False
        self.VD_expected = False
        self.DE_expected = False
        self.offd = 100 # offset to be set for ERA-I below, 100 for ERA5
        if self.project=='VOLC':
            if 'satie' in socket.gethostname():
                self.rootdir = '/dsk2/ERA5/VOLC'
            elif 'ens' in socket.gethostname():
                self.rootdir = '/net/satie/dsk2/ERA5/VOLC'
            else:
                print('unknown hostname for this dataset')
                return
            self.EN_expected = True
            self.DI_expected = True
            self.WT_expected = True
        elif project=='STC':
            if 'gort' == socket.gethostname():
                self.rootdir = '/dkol/dc6/samba/STC/ERA5/STC'
            elif 'ciclad' in socket.gethostname():
                self.rootdir = '/data/legras/flexpart_in/STC/ERA5'
            elif 'satie' in socket.gethostname():
                self.rootdir = '/dsk2/ERA5/STC'
            elif socket.gethostname() in ['grapelli','coltrane','zappa','couperin','puccini','lalo']:
                self.rootdir = '/net/satie/dsk2/ERA5/STC'
            else:
                print('unknown hostname for this dataset')
                return
            self.EN_expected = True
            self.DI_expected = True
            self.WT_expected = True
            self.VD_expected = True
        elif project=='FULL-EI':
            if 'gort' == socket.gethostname():
                self.rootdir = '/dkol/data/NIRgrid'
            elif 'ciclad' in socket.gethostname():
                self.rootdir = '/data/legras/flexpart_in/NIRgrid'
            else:
                print('unknown hostname for this dataset')
                return
            self.EN_expected = True
            self.DI_expected = True
            self.DE_expected = True
            self.offd = 300
        elif project=='FULL-EA':
            if 'gort' == socket.gethostname():
                self.rootdir = '/dkol/data/ERA5'
            elif 'ciclad' in socket.gethostname():
                self.rootdir = '/data/legras/flexpart_in/ERA5'
            else:
                print('unknown hostname for this dataset')
                return
            self.EN_expected = True
        else:
            print('Non implemented project')
            return

        #if SP_expected:
        #    self.fname = 'SP'+date.strftime('%y%m%d%H')
        #    path1 = 'SP-true/grib'
        if self.EN_expected:
            if project == 'FULL-EA':
                self.fname = date.strftime('ERA5EN%Y%m%d.grb')
                path1 ='EN-true'
            else:    
                self.fname = date.strftime('EN%y%m%d%H')           
            path1 = 'EN-true/grib'
            if project == 'FULL-EI': path1 = 'EN-true'
            self.ENvar = {'U':['u','U component of wind','m s**-1'],
                     'V':['v','V component of wind','m s**-1'],
                     'W':['w','Vertical velocity','Pa s**-1'],
                     'T':['t','Temperature','K'],
                     'LNSP':['lnsp','Logarithm of surface pressure','Log(Pa)']}
        if self.DI_expected:
            if project=='FULL-EI':
                # for ERA-I: tendencies over 3-hour intervals following file date, provided as temperature increments
                self.DIvar = {'ASSWR':['srta','Mean temperature tendency due to short-wave radiation','K'],
                     'ASLWR':['trta','Mean temperature tendency due to long-wave radiation','K'],
                     'CSSWR':['srtca','Mean temperature tendency due to short-wave radiation, clear sky','K'],
                     'CSLWR':['trtca','Mean temperature tendency due to long-wave radiation, clear sky','K'],
                     'PHR':['ttpha','Mean temperature tendency due to physics','K'],}
            else:
                # for ERA5: tendencies over 1-hour intervals following file date
                self.DIvar = {'ASSWR':['mttswr','Mean temperature tendency due to short-wave radiation','K s**-1'],
                     'ASLWR':['mttlwr','Mean temperature tendency due to long-wave radiation','K s**-1'],
                     'CSSWR':['mttswrcs','Mean temperature tendency due to short-wave radiation, clear sky','K s**-1'],
                     'CSLWR':['mttlwrcs','Mean temperature tendency due to long-wave radiation, clear sky','K s**-1'],
                     'PHR':['mttpm','Mean temperature tendency due to parametrisations','K s**-1'],
                     'UMF':['mumf','Mean updraught mass flux','kg m**-2 s**-1'],
                     'DMF':['mdmf','Mean downdraught mass flux','kg m**-2 s**-1'],
                     'UDR':['mudr','Mean updraught detrainment rate','kg m**-3 s**-1'],
                     'DDR':['mddr','Mean downdraught detrainement rate','kg m**-3 s**-1']}
            self.dname = 'DI'+date.strftime('%y%m%d%H')
        if self.WT_expected:
            # for ERA5
            self.WTvar = {'CRWC':['crwc','Specific rain water content','kg kg**-1'],
                     'CSWC':['cswc','Specific snow water content','kg kg**-1'],
                     'Q':['q','Specific humidity','kg kg**-1'],
                     'QL':['clwc','Specific cloud liquid water content','kg kg**-1'],
                     'QI':['ciwc','Specific cloud ice water content','kg kg**-1'],
                     'CC':['cc','Fraction of cloud cover','0-1']}
            self.wname = 'WT'+date.strftime('%y%m%d%H')
        if self.VD_expected:
            # for ERA5
            self.VDvar = {'DIV':['d','Divergence','s**-1'],
                          'VOR':['vo','Vorticity','s**-1'],
                          #'Z':['xxx','Geopotential','m'],
                          'WE':['etadot','Eta dot','s**-1*']}
            self.vname = 'VD'+date.strftime('%y%m%d%H')
        if self.DE_expected:
            # for ERA-I
            self.DEvar = {'UDR':['udra','Mean updraught detrainment rate','kg m**-3 s**-1']}
            self.dename = 'DE'+date.strftime('%y%m%d%H')
            
        # opening the main file    
        try:
            self.grb = pygrib.open(os.path.join(self.rootdir,path1,date.strftime('%Y/%m'),self.fname))
        except:
            try:
                self.grb = pygrib.open(os.path.join(self.rootdir,path1,date.strftime('%Y'),self.fname))
            except:
                print('cannot open '+os.path.join(self.rootdir,path1,date.strftime('%Y/%m'),self.fname))
                return
        # Define searched valid date and time
        validityDate = int(self.date.strftime('%Y%m%d'))
        validityTime = int(self.date.strftime('%H%M'))
        self.EN_open = True
        try:
            sp = self.grb.select(name='Surface pressure',validityTime=validityTime)[0]
            logp = False
        except:
            try:
                sp = self.grb.select(name='Logarithm of surface pressure',validityTime=validityTime)[0]
                logp = True
            except:
                print('no surface pressure in '+self.fname)
                self.grb.close()
                return
        # Check date matching (should be)
        if sp['validityDate'] != validityDate:
            print('WARNING: dates do not match')
            print('called date    ',self.date.strftime('%Y%m%d %H%M'))
            print('date from file ',sp['validityDate'],sp['validityTime'])
            self.grb.close()
            return
        # Get general info from this message
        self.attr['Date'] = sp['dataDate']
        self.attr['Time'] = sp['dataTime']
        self.attr['valDate'] = sp['validityDate']
        self.attr['valTime'] = sp['validityTime']
        self.nlon = sp['Ni']
        self.nlat = sp['Nj']
        self.attr['lons'] = sp['distinctLongitudes']
        self.attr['lats'] = sp['distinctLatitudes']
        # in ERA-Interim, it was necessary to divide by 1000
        if project == 'FULL-EI':
          self.attr['Lo1'] = sp['longitudeOfFirstGridPoint']/1000  # in degree
          self.attr['Lo2'] = sp['longitudeOfLastGridPoint']/1000  # in degree
          # reversing last and first for latitudes
          self.attr['La1'] = sp['latitudeOfLastGridPoint']/1000  # in degree
          self.attr['La2'] = sp['latitudeOfFirstGridPoint']/1000 # in degree
        else:
            self.attr['Lo1'] = sp['longitudeOfFirstGridPoint']/1000000  # in degree
            self.attr['Lo2'] = sp['longitudeOfLastGridPoint']/1000000  # in degree
            # reversing last and first for latitudes
            self.attr['La1'] = sp['latitudeOfLastGridPoint']/1000000  # in degree
            self.attr['La2'] = sp['latitudeOfFirstGridPoint']/1000000 # in degree
        # longitude and latitude interval
        self.attr['dlo'] = (self.attr['lons'][-1] - self.attr['lons'][0]) / (self.nlon-1)
        self.attr['dla'] = (self.attr['lats'][-1] - self.attr['lats'][0]) / (self.nlat-1) 
        if self.attr['Lo1']>self.attr['Lo2']:
            self.attr['Lo1'] = self.attr['Lo1']-360.
        if sp['PVPresent']==1 :
            pv = sp['pv']
            self.attr['ai'] = pv[0:int(pv.size/2)]
            self.attr['bi'] = pv[int(pv.size/2):]
            self.attr['am'] = (self.attr['ai'][1:] + self.attr['ai'][0:-1])/2
            self.attr['bm'] = (self.attr['bi'][1:] + self.attr['bi'][0:-1])/2
        else:
            # todo: provide a fix, eg for JRA-55
            print('missing PV not implemented')
        self.attr['levtype'] = 'hybrid'
        # Read the surface pressure
        if logp:
            self.var['SP'] = np.exp(sp['values'])
        else:
            self.var['SP'] = sp['values']
        #  Reverting lat order
        self.attr['lats'] = self.attr['lats'][::-1]
        self.var['SP']   = self.var['SP'][::-1,:]
        self.attr['dla'] = -  self.attr['dla']
        # Opening of the other files
        self.DI_open = False
        self.WT_open = False
        self.VD_open = False
        self.DE_open = False
        if self.DI_expected:
            try:
                self.drb = pygrib.open(os.path.join(self.rootdir,date.strftime('DI-true/grib/%Y/%m'),self.dname))
                self.DI_open = True
            except:
                try:
                    self.drb = pygrib.open(os.path.join(self.rootdir,date.strftime('DI-true/%Y'),self.dname))
                    self.DI_open = True 
                except:
                    print('cannot open '+os.path.join(self.rootdir,date.strftime('DI-true/grib/%Y/%m'),self.dname))
        if self.WT_expected:
            try:
                self.wrb = pygrib.open(os.path.join(self.rootdir,date.strftime('WT-true/grib/%Y/%m'),self.wname))
                self.WT_open = True
            except:
                print('cannot open '+os.path.join(self.rootdir,date.strftime('WT-true/grib/%Y/%m'),self.wname))
        if self.VD_expected:
            try:
                self.vrb = pygrib.open(os.path.join(self.rootdir,date.strftime('VD-true/grib/%Y/%m'),self.vname))
                self.VD_open = True
            except:
                print('cannot open '+os.path.join(self.rootdir,date.strftime('VD-true/grib/%Y/%m'),self.vname))
        if self.DE_expected:
            try:
                self.derb = pygrib.open(os.path.join(self.rootdir,date.strftime('DE-true/%Y'),self.dename))
                self.DE_open = True
            except:
                print('cannot open '+os.path.join(self.rootdir,date.strftime('DE-true/%Y'),self.dename))
    
    def close(self):
        self.grb.close()
        try: self.drb.close()
        except: pass
        try: self.wrb.close()
        except: pass
        try: self.derb.close()
        except: pass
        try: self.vrb.close()
        except: pass

# short cut for some common variables
    def _get_T(self):
        self._get_var('T')
    def _get_U(self):
        self._get_var('U')
    def _get_V(self):
        self._get_var('V')
    def _get_W(self):
        self._get_var('W')
    def _get_Q(self):
        self._get_var('Q')
        
# get a variable from the archive
    def _get_var(self,var):
        if var in self.var.keys():
            return
        get = False
        try:
            if self.EN_open:
                if var in self.ENvar.keys():
                    TT = self.grb.select(shortName=self.ENvar[var][0],validityTime=self.attr['valTime'])
                    get = True
            if self.DI_open:
                if var in self.DIvar.keys():
                    TT = self.drb.select(shortName=self.DIvar[var][0],validityTime=(self.attr['valTime']+self.offd) % 2400)
                    get = True
            if self.WT_open:
                if var in self.WTvar.keys():
                    TT = self.wrb.select(shortName=self.WTvar[var][0],validityTime=self.attr['valTime'])
                    get = True
            if self.VD_open:
                if var in self.VDvar.keys():
                    TT = self.vrb.select(shortName=self.VDvar[var][0],validityTime=self.attr['valTime'])
                    get = True
            if self.DE_open:
                if var in self.DEvar.keys():
                    # Shift of validity time due to ERA-I convention
                    TT = self.derb.select(shortName=self.DEvar[var][0],validityTime=(self.attr['valTime']+self.offd) % 2400)
                    get = True
            if get == False:
                print(var+' not found')
        except:
            print(var+' not found or read error')
            return
        # Process each message corresponding to a level
        if 'levs' not in self.attr.keys():
            readlev=True
            self.nlev = len(TT)
            self.attr['levs'] = np.full(len(TT),MISSING,dtype=int)
            self.attr['plev'] = np.full(len(TT),MISSING,dtype=int)
        else:
            readlev=False
            if len(TT) !=  self.nlev:
                print('new record inconsistent with previous ones')
                return
        self.var[var] = np.empty(shape=[self.nlev,self.nlat,self.nlon])
        #print(np.isfortran(self.var[var]))

        for i in range(len(TT)):
            self.var[var][i,:,:] = TT[i]['values']
            if readlev:
                try:
                    lev = TT[i]['lev']
                except:
                    pass
                try:
                    lev = TT[i]['level']
                except:
                    pass
                self.attr['levs'][i] = lev
                self.attr['plev'][i] = self.attr['am'][lev-1] + self.attr['bm'][lev-1]*cst.pref

#       # Check the vertical ordering of the file
        if readlev:
            if not strictly_increasing(self.attr['levs']):
                self.warning.append('NOT STRICTLY INCREASING LEVELS')
        # Reverting North -> South to South to North
        #print(np.isfortran(self.var[var]))
        self.var[var] = self.var[var][:,::-1,:]
        #print(np.isfortran(self.var[var]))
        return None
    
    def get_var(self,var):
        self._get_var(var)
        return self.var['var' ]

    def _mkp(self):
        # Calculate the pressure field
        self.var['P'] =  np.empty(shape=(self.nlev,self.nlat,self.nlon))
        for i in range(self.nlev):
            lev = self.attr['levs'][i]
            self.var['P'][i,:,:] = self.attr['am'][lev-1] \
                                 + self.attr['bm'][lev-1]*self.var['SP']

    def _mkpz(self):
        # Calculate pressure field for w (check)
        self.var['PZ'] =  np.empty(shape=(self.nlev,self.nlat,self.nlon))
        for i in range(self.nlev):
            lev = self.attr['levs'][i]
            self.var['PZ'][i,:,:] = self.attr['ai'][lev-1] \
                                  + self.attr['bi'][lev-1]*self.var['SP']
                                  
    def _mkpscale(self):
        # Define the standard pressure scale for this vertical grid
        self.attr['pscale'] = self.attr['am'] + self.attr['bm'] * 101325

    def _mkthet(self):
        # Calculate the potential temperature
        if not set(['T','P']).issubset(self.var.keys()):
            print('T or P undefined')
            return
        self.var['PT'] = self.var['T'] * (cst.p0/self.var['P'])**cst.kappa

    def _mkrho(self):
        # Calculate the dry density
        if not set(['T','P']).issubset(self.var.keys()):
            print('T or P undefined')
            return
        self.var['RHO'] = (1/cst.R) * self.var['P'] / self.var['T']

    def _mkrhoq(self):
        # Calculate the moist density
        if not set(['T','P','Q']).issubset(self.var.keys()):
            print('T, P or Q undefined')
            return
        pcor = 230.617*self.var['Q']*np.exp(17.5043*self.var['Q']/(241.2+self.var['Q']))
        self.var['RHO'] = (1/cst.R) * (self.var['P'] - pcor) / self.var['T']

    def _checkThetProfile(self):
        # Check that the potential temperature is always increasing with height
        if 'PT' not in self.var.keys():
            print('first calculate PT')
            return
        ddd = self.var['PT'][:-1,:,:]-self.var['PT'][1:,:,:]
        for lev in range(ddd.shape[0]):
            if np.min(ddd[lev,:,:]) < 0:
                print('min level of inversion: ',lev)
                return lev
            
    def _mkz(self):
        """ Calculate the geopotential without taking moiture into account """
        if not set(['T','P']).issubset(self.var.keys()):
            print('T or P undefined')
            return
        try:
            with gzip.open(os.path.join(self.rootdir,'EN-true','Z0_'+self.project+'.pkl')) as f:
                Z0 = pickle.load(f)
        except:
            print('Cannot read ground geopotential')
        self.var['Z0'] = Z0.var['Z0']
        self.var['Z'] =  np.empty(shape=self.var['T'].shape)
        uu = - np.log(self.var['P'])
        uusp = -np.log(self.var['SP'])
        self.var['Z'][self.nlev-1,:,:] = self.var['Z0'] \
               + (cst.R/cst.g) * self.var['T'][self.nlev-1,:,:] \
               * (uu[self.nlev-1,:,:]-uusp)
        for i in range(self.nlev-2,-1,-1):
             self.var['Z'][i,:,:] = self.var['Z'][i+1,:,:] + 0.5*(cst.R/cst.g) \
                    * (self.var['T'][i,:,:] + self.var['T'][i+1,:,:])\
                    * (uu[i,:,:]-uu[i+1,:,:])
            
if __name__ == '__main__':
    date = datetime(2017,8,11,18)
    dat = ECMWF('STC',date)
    dat._get_T()
    dat._get_U()
    dat._get_var('ASLWR')
    #dat._get_var('CC')
    dat._mkp()
    dat._mkthet()
    dat._checkThetProfile()
