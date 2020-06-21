import numpy as np 
from PIL import Image
from scipy.io import loadmat,savemat
from array import array
import torch

# define facemodel for reconstruction
class BFM():
    def __init__(self):
        model_path = './BFM/BFM_model_front.mat'
        model = loadmat(model_path)
        """
        self.meanshape = model['meanshape'] # mean face shape 
        self.idBase = model['idBase'] # identity basis
        self.exBase = model['exBase'] # expression basis
        self.meantex = model['meantex'] # mean face texture
        self.texBase = model['texBase'] # texture basis
        self.point_buf = model['point_buf'] # adjacent face index for each vertex, starts from 1 (only used for calculating face normal)
        self.tri = model['tri'] # vertex index for each triangle face, starts from 1
        self.keypoints = np.squeeze(model['keypoints']).astype(np.int32) - 1 # 68 face landmark index, starts from 0
        """

        self.meanshape = torch.tensor(model['meanshape']).float() 
        self.idBase = torch.tensor(model['idBase']).float() # identity basis
        self.exBase = torch.tensor(model['exBase']).float() # expression basis
        self.meantex = torch.tensor(model['meantex']).float() # mean face texture
        self.texBase = torch.tensor(model['texBase']).float() # texture basis
        self.point_buf = torch.tensor(model['point_buf']).float() # adjacent face index for each vertex, starts from 1 (only used for calculating face normal)
        self.tri = torch.tensor(model['tri']).long() # vertex index for each triangle face, starts from 1
        self.keypoints = torch.tensor(np.squeeze(model['keypoints']).astype(np.int32) - 1).long() # 68 face landmark index, starts from 0
        self.skinmask = torch.tensor(model['skinmask'][0].astype(np.int32)).long()


    def set_device(self, device):
        #-----turn to pytorch
        """
        self.meanshape = torch.tensor(self.meanshape).float().to(device)
        self.idBase = torch.tensor(self.idBase).float().to(device)
        self.exBase = torch.tensor(self.exBase).float().to(device)
        self.meantex = torch.tensor(self.meantex).float().to(device)
        self.texBase = torch.tensor(self.texBase).float().to(device)
        self.point_buf = torch.tensor(self.point_buf).long().to(device)
        self.tri = torch.tensor(self.tri).long().to(device)
        self.keypoints = torch.tensor(self.keypoints).long().to(device)
        """

        self.meanshape = self.meanshape.to(device)
        self.idBase = self.idBase.to(device)
        self.exBase = self.exBase.to(device)
        self.meantex = self.meantex.to(device)
        self.texBase = self.texBase.to(device)
        self.point_buf = self.point_buf.to(device)
        self.tri = self.tri.to(device)
        self.keypoints = self.keypoints.to(device)
        self.skinmask = self.skinmask.to(device)

# load expression basis
def LoadExpBasis():
    n_vertex = 53215
    Expbin = open('BFM/Exp_Pca.bin','rb')
    exp_dim = array('i')
    exp_dim.fromfile(Expbin,1)
    expMU = array('f')
    expPC = array('f')
    expMU.fromfile(Expbin,3*n_vertex)
    expPC.fromfile(Expbin,3*exp_dim[0]*n_vertex)

    expPC = np.array(expPC)
    expPC = np.reshape(expPC,[exp_dim[0],-1])
    expPC = np.transpose(expPC)

    expEV = np.loadtxt('BFM/std_exp.txt')

    return expPC,expEV

# transfer original BFM09 to our face model
def transferBFM09():
    original_BFM = loadmat('BFM/01_MorphableModel.mat')
    shapePC = original_BFM['shapePC'] # shape basis
    shapeEV = original_BFM['shapeEV'] # corresponding eigen value
    shapeMU = original_BFM['shapeMU'] # mean face
    texPC = original_BFM['texPC'] # texture basis
    texEV = original_BFM['texEV'] # eigen value
    texMU = original_BFM['texMU'] # mean texture

    expPC,expEV = LoadExpBasis()

    # transfer BFM09 to our face model

    idBase = shapePC*np.reshape(shapeEV,[-1,199])
    idBase = idBase/1e5 # unify the scale to decimeter
    idBase = idBase[:,:80] # use only first 80 basis

    exBase = expPC*np.reshape(expEV,[-1,79])
    exBase = exBase/1e5 # unify the scale to decimeter
    exBase = exBase[:,:64] # use only first 64 basis

    texBase = texPC*np.reshape(texEV,[-1,199])
    texBase = texBase[:,:80] # use only first 80 basis

    # our face model is cropped align face landmarks which contains only 35709 vertex.
    # original BFM09 contains 53490 vertex, and expression basis provided by JuYong contains 53215 vertex.
    # thus we select corresponding vertex to get our face model.

    index_exp = loadmat('BFM/BFM_front_idx.mat')
    index_exp = index_exp['idx'].astype(np.int32) - 1 #starts from 0 (to 53215)

    index_shape = loadmat('BFM/BFM_exp_idx.mat')
    index_shape = index_shape['trimIndex'].astype(np.int32) - 1 #starts from 0 (to 53490)
    index_shape = index_shape[index_exp]


    idBase = np.reshape(idBase,[-1,3,80])
    idBase = idBase[index_shape,:,:]
    idBase = np.reshape(idBase,[-1,80])

    texBase = np.reshape(texBase,[-1,3,80])
    texBase = texBase[index_shape,:,:]
    texBase = np.reshape(texBase,[-1,80])

    exBase = np.reshape(exBase,[-1,3,64])
    exBase = exBase[index_exp,:,:]
    exBase = np.reshape(exBase,[-1,64])

    meanshape = np.reshape(shapeMU,[-1,3])/1e5
    meanshape = meanshape[index_shape,:]
    meanshape = np.reshape(meanshape,[1,-1])

    meantex = np.reshape(texMU,[-1,3])
    meantex = meantex[index_shape,:]
    meantex = np.reshape(meantex,[1,-1])

    # other info contains triangles, region used for computing photometric loss,
    # region used for skin texture regularization, and 68 landmarks index etc.
    other_info = loadmat('BFM/facemodel_info.mat')
    frontmask2_idx = other_info['frontmask2_idx']
    skinmask = other_info['skinmask']
    keypoints = other_info['keypoints']
    point_buf = other_info['point_buf']
    tri = other_info['tri']
    tri_mask2 = other_info['tri_mask2']

    # save our face model
    savemat('BFM/BFM_model_front.mat',{'meanshape':meanshape,'meantex':meantex,'idBase':idBase,'exBase':exBase,'texBase':texBase,'tri':tri,'point_buf':point_buf,'tri_mask2':tri_mask2\
        ,'keypoints':keypoints,'frontmask2_idx':frontmask2_idx,'skinmask':skinmask})

# load landmarks for standard face, which is used for image preprocessing
def load_lm3d():

    Lm3D = loadmat('./BFM/similarity_Lm3D_all.mat')
    Lm3D = Lm3D['lm']

    # calculate 5 facial landmarks using 68 landmarks
    lm_idx = np.array([31,37,40,43,46,49,55]) - 1
    Lm3D = np.stack([Lm3D[lm_idx[0],:],np.mean(Lm3D[lm_idx[[1,2]],:],0),np.mean(Lm3D[lm_idx[[3,4]],:],0),Lm3D[lm_idx[5],:],Lm3D[lm_idx[6],:]], axis = 0)
    Lm3D = Lm3D[[1,2,0,3,4],:]

    return Lm3D

# load input images and corresponding 5 landmarks
def load_img(img_path,lm_path):

    image = Image.open(img_path)
    lm = np.loadtxt(lm_path)

    return image,lm

# save 3D face to obj file
def save_obj(path,v,f,c):
    with open(path,'w') as file:
        for i in range(len(v)):
            file.write('v %f %f %f %f %f %f\n'%(v[i,0],v[i,1],v[i,2],c[i,0],c[i,1],c[i,2]))

        file.write('\n')

        for i in range(len(f)):
            file.write('f %d %d %d\n'%(f[i,0],f[i,1],f[i,2]))

    file.close()
