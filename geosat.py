#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr  6 15:08:05 2017

This module is made to give easy acccess to the GEO data and project them onto 
rectangular longitude-latitude grids. The data are used in their native geometry 
from netcdf files. 
At the moment (MAy 2017), this module can be used for Himawari (2km files) and the MSG satellites.

Functions:
- read the satellite channels
- perform zenith angle correction on the 10.8µm channel using the method of Joyce (contained in a 
separate module) 
- project onto a set of predefined rectangular grids in longitude-latitude
- make nice charts on these grids
- interpolate in time between two satellite time slot (based on nominal time)
- define a daughter grid that is a subset of one of the predefined grids and extract the fields on this grid
- patch images from two GEO at a given longitude onto a grid

The module relies on a number of external files that define lat-lon satellite grids, mask of the earth disk 
in the native satellite geometry, and lookup table for the projections. The lat-lon and mask data are generated
aoutside of this module. The lookup table are generated by the module, once for ever, for each association of
a grid with a GEO.

TO DO: usage doc
Look in the test-geosat directory for examples of usages 

@author: Bernard Legras
"""

from netCDF4 import Dataset
import numpy as np
#import tables
import socket
import os
import pickle,gzip
from scipy.interpolate import NearestNDInterpolator
from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt
import sza_correc

if socket.gethostname() == 'graphium':
    sats_dir = 'C:\\cygwin64\\home\\Bernard\\data\\sats'
    root_dir = 'C:\\cygwin64\\home\\Bernard\\data\\sats'
    gridsat = 'C:\\cygwin64\\home\\Bernard\\data\\sats'
elif 'ciclad' in socket.gethostname():
    sats_dir = '/data/legras/sats'
    root_dir = '/bdd/STRATOCLIM/data'
    gridsat = 'undefined'
elif ('climserv' in socket.gethostname()) | ('polytechnique' in socket.gethostname()):
    sats_dir = '/home/stratocl/TRAJ/pylib'
    root_dir = '/bdd/STRATOCLIM/data'
    gridsat = 'undefined'
elif socket.gethostname() == 'grapelli':
    sats_dir = '/limbo/data/sats'
    root_dir = '/limbo/data/sats'
    gridsat =  '/limbo/data/sats'
elif socket.gethostname() == 'zappa':
    # to be adjusted
     sats_dir = '/net/grapelli/limbo/data/sats'
     root_dir = '/net/grapelli/limbo/data/sats'
     gridsat =  '/net/grapelli/limbo/data/sats'
elif socket.gethostname() == 'gort':
     sats_dir = '/dkol/data/sats'
     root_dir = '/dkol/data/sats'
     gridsat =  '/dkol/data/sats'     
else:
     print ('CANNOT RECOGNIZE HOST - DO NOT RUN ON NON DEFINED HOSTS')

# This mask is made to palliate the incomplete masking of himawari data 
# and the supposedly moving mask of MSG satellites    
mask_sat={}
lonlat_sat={}

def read_mask_himawari():
    mask_sat['himawari'] = pickle.load(gzip.open(os.path.join(root_dir,'himawari','mask.pkl'),'rb'))
def read_mask_MSG():
    # change after 14/05/2017: use the mask based on the data and not that from the lonlat file  
    mask_sat['msg'] = pickle.load(gzip.open(os.path.join(root_dir,'msg1','mask.pkl'),'rb'))
def read_lonlat(sat):
    if sat == 'msg1':
        satin = 'msg3'
    else:
        satin = sat
    lonlat_sat[sat] = pickle.load(gzip.open(os.path.join(root_dir,satin,'lonlat.pkl'),'rb'))
    if sat == 'msg1':
       lonlat_sat[sat]['lon'] += 41.5

#%%
class PureSat(object):
    ''' mother class of GeoSat that allows to define derived objects from
    data read with GeoSat class    
    '''
    def __init__(self,sat):
        self.var={}
        self.sat = sat
        
    def show(self,field,clim=[190.,300.],txt=''):
        ''' Shows the field in the satelliet geometry '''
        if field not in self.var:
            print('undefined field')
            return
        fig = plt.figure()
        iax=plt.imshow(self.var[field],clim=clim)
        cax = fig.add_axes([0.91, 0.15, 0.03, 0.7])
        fig.colorbar(iax, cax=cax)
        fig.suptitle(txt)
        plt.show()
        
    def provide_1D(self,var):
        ''' Returns a compressed 1D field from a masked array 
        '''
        return self.var[var].compressed()
    
    def _sza_correc(self):
        ''' Correction of the brightness temperature of the IR0 channel.
        '''
        print ('entering correction PureSat version')
        if 'IR0' not in self.var.keys():
            print ('IR0 must be defined')
            return
        try:
            sat = self.sat
        except:
            print ('sat non defined')
            return
        
        if sat not in lonlat_sat.keys():
            read_lonlat(sat)
        # generates repeated lon and lat     
        sza,_ = sza_correc.szacorr(self.date,self.var['IR0'].flatten(),
                    lonlat_sat[sat]['lon'].flatten(),lonlat_sat[sat]['lat'].flatten(),
                    self.sublon,self.sublat)
        self.var['IR0'] += sza.reshape([self.nlat,self.nlon])
        return
               
class GeoSat(PureSat):
    '''
    Generic parent class to read geostationary netcdf objects.
    Use product-specific classes instead.
    '''
    def __init__(self, filename):
        '''
        filename : name of the geostationay file
        '''
        self.ncid = Dataset(filename, mode='r')
        
        # loads the mask if needed
        if ('hima' in filename) & ('himawari' not in mask_sat.keys()):
            read_mask_himawari()
        if ('msg' in filename) & ('msg' not in mask_sat.keys()):
            read_mask_MSG()
        try:     
            PureSat.__init__(self,self.sat)
        except:
            PureSat.__init__(self,'unknown')
            
        self.sublon = self.ncid.variables['satellite'].lon
        self.sublat = self.ncid.variables['satellite'].lat
        self.dst = self.ncid.variables['satellite'].dst 
        try:
            self.nlon = len(self.ncid.dimensions['nx'])
            self.nlat =len(self.ncid.dimensions['ny'])
        except:
            self.nlon = len(self.ncid.dimensions['nx2km'])
            self.nlat =len(self.ncid.dimensions['ny2km'])                      
                               
    def close(self):
        self.ncid.close()
         
    def get_IR0(self):
        ''' Reads the infrared window if not already stored, stores and returns it '''
        if 'IR0' not in self.var.keys():
            self._get_IR0()
        return self.var['IR0']
    
    def get_var(self,field):
        ''' Reads a general variable if not already stored, so needed, stores and returns it ''' 
        if field not in self.var.keys():
            self._get_var(field)
        return self.var[field]
        
    
    def degrad_IR0(self):
        ''' Makes a new geosat image with averaged total radiance from the estimated brightness temperature
        '''
        target=PureSat()
        radiance = self.var['IR0']**4
        toto_radiance = 0.5 * (radiance[range(0, radiance.shape[0], 2), :] +
                           radiance[range(1, radiance.shape[0], 2), :])
        target.var['IR0'] = (0.5 * (toto_radiance[:, range(0, toto_radiance.shape[1], 2)] +
                 toto_radiance[:, range(1, toto_radiance.shape[1], 2)])) ** (1. / 4.)
        target.sat = self.sat
        target.sublon = self.sublon
        target.sublat = self.sublat
        target.nlat = target.var['IR0'].shape[0]
        target.nlon = target.var['IR0'].shape[1]
        return target
        
    
class MSG(GeoSat):
    
    def __init__(self, filename):
        GeoSat.__init__(self,filename)
            
    def _get_IR0(self):
        '''
        Reads the infrared windows and stores a masked array in self
        '''
        self.var['IR0'] = np.ma.array(self.ncid.variables['IR_108'][:],mask=mask_sat['msg'])
        self.var['IR0']._sharedmask=False
        return
    
    def _get_var(self,field):
        '''
        Reads a general variable and stores a masked array in self
        '''
        self.var[field] = np.ma.array(self.ncid.variables[field][:],mask=mask_sat['msg'])
        self.var[field]._sharedmask=False
        return
        
class MSG1(MSG):
    def __init__(self,date):
        self.sat = 'msg1'
        self.date =  date
        file = 'Imultic3kmNC4_msg01_' + date.strftime("%Y%m%d%H%M") + '.nc'
        fullname = os.path.join(root_dir, 'msg1', 'netcdf', 
                date.strftime("%Y"), date.strftime("%Y_%m_%d"),file)
        MSG.__init__(self,fullname)
        
class MSG3(MSG):
    def __init__(self,date):
        self.sat='msg3'
        self.date =  date
        file = 'Mmultic3kmNC4_msg03_' + date.strftime("%Y%m%d%H%M") + '.nc'
        fullname = os.path.join(root_dir, 'msg3', 'netcdf', 
                date.strftime("%Y"), date.strftime("%Y_%m_%d"),file)
        MSG.__init__(self,fullname)        
        
class Himawari(GeoSat):
    def __init__(self,date):
        self.sat = 'himawari'
        self.date =  date
        self.file = 'Jmultic2kmNC4_hima08_' + date.strftime("%Y%m%d%H%M") + '.nc'
        self.fullname = os.path.join(root_dir, 'himawari', 'netcdf', 
                date.strftime("%Y"), date.strftime("%Y_%m_%d"),self.file)
        GeoSat.__init__(self,self.fullname)
       
    def _get_IR0(self):       
        self.var['IR0'] = self.ncid.variables['IR_104'][:] 
        self.var['IR0'].__setmask__(mask_sat['himawari'])
        self.var['IR0']._sharedmask=False
        return
    
    def _get_var(self,field):
        self.var[field] = self.ncid.variables[field][:] 
        self.var[field].__setmask__(mask_sat['himawari'])
        self.var[field]._sharedmask=False
        return
    
  
#%%        
class GeoGrid(object):
    '''
    Defines the attributes of the grid.
    '''
    def __init__(self, gridtype,box=None,bins=None):
        self.gridtype = gridtype
        if gridtype == "FullAMA":
            self.box_range = np.array([[-10.,160.], [0.,50.]])
            self.box_binx = 1700; self.box_biny = 500
        elif gridtype == "HimFull":
            self.box_range = np.array([[60.,220.],[-80.,80.]])
            self.box_binx = 4000; self.box_biny = 4000;
        elif gridtype == "MSG1Full":
            self.box_range = np.array([[-38.5,121.5],[-80,80]])
            self.box_binx = 4000; self.box_biny = 4000;
        elif gridtype == "MSG3Full":
            self.box_range = np.array([[-80,80],[-80,80]])
            self.box_binx = 4000; self.box_biny = 4000;
        elif gridtype == "NAG":
            self.box_range = np.array([[67.5,91.5],[9.,33.]])
            self.box_binx = 240; self.box_biny = 240;
        elif gridtype == "KTM":
            self.box_range = np.array([[73.,97.],[15.,39.]])
            self.box_binx = 240; self.box_biny = 240;
        elif gridtype == "KLM":
            self.box_range = np.array([[10.,35.],[25.,45.]])
            self.box_binx = 200; self.box_biny = 200;
        elif gridtype == "MesoMed":
            self.box_range = np.array([[-10.,50.],[20.,45.]])
            self.box_binx = 600; self.box_biny = 250;
        elif gridtype == "MesoInd":
            self.box_range = np.array([[65.,130.],[5.,40.]])
            self.box_binx = 650; self.box_biny = 350;
        elif gridtype == "GridSat":
            # pixels of 0.07 degree slightly overmatch
            self.box_range = np.array([[0.,360.01],[-70.,70.]])
            self.box_binx = 5143; self.box_biny = 2000;
        else:
            if bins==None:
                print("Unknown gridtype")
                raise NameError
            else:
                self.gridtype = gridtype
                self.box_range = box
                self.box_binx = bins[0]
                self.box_biny = bins[1]
                
        self.xedge = np.arange(self.box_range[0,0], self.box_range[0,1]+0.001,
                   (self.box_range[0,1]-self.box_range[0,0])/self.box_binx)
        self.yedge = np.arange(self.box_range[1,0], self.box_range[1,1]+0.001,
                   (self.box_range[1,1]-self.box_range[1,0])/self.box_biny)
        self.xcent = 0.5*(self.xedge[range(0, len(self.xedge)-1)]+self.xedge[range(1, len(self.xedge))])
        self.ycent = 0.5*(self.yedge[range(0, len(self.yedge)-1)]+self.yedge[range(1, len(self.yedge))])
        self.shapeyx = [len(self.ycent),len(self.xcent)]
        self.shapexy = [len(self.xcent),len(self.ycent)]

    def subgrid(self,bounds):        
        ''' Generates a subgrid with name temp that is a daughter of the main 
        and can be used to make plots in a subdomain using standard plot'''
        try:
            [Lo1,Lo2,La1,La2] = bounds
        except:
            print ("badly shaped box")
        # first check that the boundaries are within the mother grid
        if (Lo1 > self.box_range[0,1]) | (Lo1 < self.box_range[0,0]):
            print ('Lo1 outside bounds')
        if (Lo2 > self.box_range[0,1]) | (Lo2 < self.box_range[0,0]):
            print ('Lo2 outside bounds')
        if (La1 > self.box_range[1,1]) | (Lo1 < self.box_range[1,0]):
            print ('La1 outside bounds')
        if (La2 > self.box_range[1,1]) | (Lo1 < self.box_range[1,0]):
            print ('La2 outside bounds')
        # find boundaries
        eps=0.0001
        lowlon = np.where(self.xedge-Lo1-eps<=0)[0][-1]
        higlon = np.where(self.xedge-Lo2+eps>=0)[0][0]
        lowlat = np.where(self.yedge-La1-eps<=0)[0][-1]
        higlat = np.where(self.yedge-La2+eps>=0)[0][0]
        print(lowlon,higlon,lowlat,higlat)
        # create new object
        other = GeoGrid("temp",box=np.array([[self.xedge[lowlon],self.xedge[higlon]],
                                    [self.yedge[lowlat],self.yedge[higlat]]]),
                                    bins =[higlon-lowlon,higlat-lowlat])
        other.mothergrid = self.gridtype
        other.corner = [lowlon,lowlat]
        return other
             
    def _mkandsav_lookup(self,sat):
        ''' Generates the lookup table for a pair sat and grid.
        Usage: first generate the grid object 
               gg = geosat.GeoGrid(gridtype) 
               where gridtype is one of the allowed grids
               then runs the generator for this grid and a given satellite 
               (it takes a while)
               gg._mkandsav_lookup(sat)
               sat can take values among himawari, msg1, msg3
        '''       
              
        # get the lon lat grid from the satellite
        try:
            if sat == 'msg1':
                satin = 'msg3'
            else:
                satin = sat
            print(os.path.join(root_dir,satin,'lonlat.pkl'))    
            lonlat = pickle.load(gzip.open(os.path.join(root_dir,satin,'lonlat.pkl'),'rb'))
            # add 360 to avoid discontinuity at 180 for Himawari
            if sat == 'himawari':
                lonlat['lon'][lonlat['lon']<0] += 360
            # add 41.5 degree to msg3 lon to get msg1 lon
            if sat == 'msg1':
                lonlat['lon'] += 41.5
            # Flatten the grid and select only the non masked pixels
            lonlat_c = np.asarray([lonlat['lon'].compressed(), lonlat['lat'].compressed()])
        except:
            print ('sat or lonlat undefined')
            return
        # Calculate interpolator index
        idx = np.arange(lonlat_c.shape[1], dtype=int) 
        print('NearestNDInterpolator start')
        interp = NearestNDInterpolator(lonlat_c.T,idx)
        print('NearestNDInterpolator done')
        # Building the lookup table for the grid
        lookup = np.empty(shape=(len(self.ycent),len(self.xcent)), dtype=int)
        for j in range(len(self.ycent)):
            lookup[j,:] = interp(np.asarray([self.xcent,np.repeat(self.ycent[j],len(self.xcent))]).T)
        self.lookup_dict={}
        self.lookup_dist={}
        self.lookup_dict['lat_g']=self.ycent
        self.lookup_dict['lon_g']=self.xcent
        self.lookup_dict['lookup_f']=lookup.flatten()
        # Calculate actual distances between pixels on the regular grid and the
        # closest neighbour on the Himawari grid that can be used to generate a
        # mask to disclose meshes which are too far from their nearest neighbour
        # distance is in a regular lon lat space
        self.lookup_dist['distx']=abs(np.repeat([self.xcent],len(self.ycent),axis=0).flatten()-(lonlat['lon'].compressed())[self.lookup_dict['lookup_f']])
        self.lookup_dist['disty']=abs((np.repeat([self.ycent],len(self.xcent),axis=0).T).flatten()-(lonlat['lat'].compressed())[self.lookup_dict['lookup_f']])
        # Calculate a mask with distance less than 0.2 in longitude or latitude
        offset=0.2
        self.lookup_dict['mask']=(self.lookup_dist['distx']>offset) | (self.lookup_dist['disty']>offset)
        # Add lonlat mask to the dist as this is useful to process the data (highly compressible)
        #self.lookup_dict['in_mask'] = lonlat['lon'].mask
        # Store the lookup table and distances separately
        pickle.dump(self.lookup_dict,gzip.open(os.path.join(root_dir,sat,
              'lookup_'+sat+'_'+self.gridtype+'.pkl'),'wb',pickle.HIGHEST_PROTOCOL))
        pickle.dump(self.lookup_dist,gzip.open(os.path.join(root_dir,sat,
              'lookup_dist_'+sat+'_'+self.gridtype+'.pkl'),'wb',pickle.HIGHEST_PROTOCOL))

#%%        
class GridField(object):
    ''' 
    Data object on a grid. Expect a valid GeoGrid object as argument '''
    
    
    def __init__(self, geogrid):
        try:
            self.geogrid = geogrid
            self.gridtype = geogrid.gridtype
        except:
            print ('geogrid object basdly defined')
            return
        # Initializes var disctionary
        self.var={}
    
    def chart(self,field,clim=[190.,300.],txt='',subgrid=None):
        # test existence of key field
        if field not in self.var.keys():
            print ('undefined field')
            return
        if subgrid == None:
            geogrid = self.geogrid
        else:
            geogrid = subgrid
        if geogrid.gridtype == 'FullAMA':
            fig = plt.figure(figsize=[10, 6])
        else:
            fig = plt.figure()  
        m = Basemap(projection='cyl', llcrnrlat=geogrid.box_range[1, 0], urcrnrlat=geogrid.box_range[1, 1],
                llcrnrlon=geogrid.box_range[0, 0], urcrnrlon=geogrid.box_range[0, 1], resolution='c')
        m.drawcoastlines(color='k')
        m.drawcountries(color='k')
        if geogrid.box_range[0, 1] - geogrid.box_range[0, 0] <= 50.:
            spacex = 5.
        else:
            spacex = 10.
        if geogrid.box_range[1, 1] - geogrid.box_range[1, 0] <= 50.:
            spacey = 5.
        else:
            spacey = 10.
        meridians = np.arange(geogrid.box_range[0, 0], geogrid.box_range[0, 1], spacex)
        parallels = np.arange(geogrid.box_range[1, 0], geogrid.box_range[1, 1], spacey)
        m.drawmeridians(meridians, labels=[0, 0, 0, 1], fontsize=8)
        m.drawparallels(parallels, labels=[1, 0, 0, 0], fontsize=8)
        if subgrid==None:
            plotted_field = self.var[field]
        else:
            # extraction in subgrid
            plotted_field = self.var[field][geogrid.corner[0]:geogrid.corner[0]+geogrid.box_binx,
                                            geogrid.corner[1]:geogrid.corner[1]+geogrid.box_biny]
        iax = plt.imshow(plotted_field, interpolation='nearest', extent=geogrid.box_range.flatten(),
                     clim=clim, origin='lower', aspect=1.)
        cax = fig.add_axes([0.91, 0.15, 0.03, 0.7])
        plt.colorbar(iax, cax=cax)
        plt.title(txt)
        plt.show()
        return None

    def patch(self,other,lon,var):
        ''' Patch two fields on the same grid at a given longitude given by lon'''
        
        if self.gridtype != other.gridtype:
            print('error: grids do not match')
            return -1
        
        patched = GridField(self.geogrid)
        patching_x = np.where(self.geogrid.xcent > lon)[0][0]
        if type(var) == str:
            var1 = [var,]
        else:
            var1 = var
        for vv in var1:
            patched.var[vv] = np.empty(shape=(len(self.geogrid.ycent),len(self.geogrid.xcent)))
            patched.var[vv][:,:patching_x] = self.var[vv][:,:patching_x]
            patched.var[vv][:,patching_x:] = other.var[vv][:,patching_x:]
        return patched
        
#%%   
class SatGrid(GridField):    
    ''' Associates a geosat object to a grid, both being predefined '''
    def __init__(self, geosat, geogrid):
        try:
            GridField.__init__(self,geogrid)
            self.geosat = geosat
            self.sat = geosat.sat
            self.cname = self.sat + '_' + self.gridtype
        except:
            print ('geosat object basdly defined')
            return 
        # test whether the corresponding lookup table is loaded
        global lookup, lookup_dist
        try:
            if self.cname not in lookup.keys():
                raise NameError
        except:
            # try to load the lookup table
            if 'lookup' not in globals():
                lookup = {}
                lookup_dist = {}
            try:
                lookup[self.cname]=pickle.load(gzip.open(os.path.join(root_dir,self.sat,'lookup_'+self.cname+'.pkl'),'rb'))
                lookup_dist[self.cname]=pickle.load(gzip.open(os.path.join(root_dir,self.sat,'lookup_dist_'+self.cname+'.pkl'),'rb'))
                           
            except:
                print ('Lookup table for this grid and sat does not exist yet.')
                print ('Must be done prior to creation of this object.' )

#%%                
    def _sat_togrid(self,field):
        ''' Conversion to the grid using lookup table '''
        # check that the field has been read
        if field not in self.geosat.var.keys():
            print ('field must be read before conversion to grid')
            return
        self.var[field] = np.ma.array(self.geosat.var[field].compressed()[lookup[self.cname]['lookup_f']].reshape(self.geogrid.shapeyx),
                       mask=lookup[self.cname]['mask'].reshape(self.geogrid.shapeyx))
        return 
        
    def _sza_correc(self):
        ''' Correction of the brightness temperature of the IR0 channel.
        '''
        print('entering sza_correction SatGrid version')
        if 'IR0' not in self.var.keys():
            print ('IR0 must be defined')
            return
        # generates repeated lon and lat     
        llons = np.repeat([self.geogrid.xcent],len(self.geogrid.ycent),axis=0).flatten()
        llats = (np.repeat([self.geogrid.ycent],len(self.geogrid.xcent),axis=0).T).flatten()
        sza,_ = sza_correc.szacorr(self.geosat.date,self.var['IR0'].flatten(),llons,llats,self.geosat.sublon,self.geosat.sublat)
        self.var['IR0'] += sza.reshape(self.geogrid.shapeyx)
        return
        

