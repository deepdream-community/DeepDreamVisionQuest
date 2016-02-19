#!/usr/bin/python
__author__ = 'Gary Boodhoo'

# TODO: not needing all of these imports. cleanup
import argparse
import os, os.path
import re
import errno
import sys
import time
import subprocess
from random import randint
from cStringIO import StringIO
import numpy as np
import scipy.ndimage as nd
import PIL.Image 
from google.protobuf import text_format
import cv2

os.environ['GLOG_minloglevel'] = '2'    # suppress verbose caffe logging
import caffe

# GRB: must it be like this? seems sloppy
net = None # will become global reference to the network model once inside the loop

# viewport
viewport_w, viewport_h = 1280,720 # display resolution

# camera object
cap = cv2.VideoCapture(0)
cap_w, cap_h = 1280,720 # capture resolution
cap.set(3,cap_w)
cap.set(4,cap_h)


# motion detection - prepopulate queue before we enter the loop
t_minus = cap.read()[1]
t_now = cap.read()[1]
t_plus = cap.read()[1]
delta_count_last = 1
record_video_state = False
DELTA_COUNT_THRESHOLD = 80000

# this creates a RGB image from our image matrix
def showarray(window_name, a):
    # convert and clip our floating point matrix into 0-255 values for RGB image
    a = np.uint8(np.clip(a, 0, 255))

    # resize takes its arguments as w,h in that order
    dim = (viewport_w, viewport_h)
    a = cv2.resize(a, dim, interpolation = cv2.INTER_LINEAR)

    # write text to image buffer
    message = 'delta_count_last: {:10d}'.format(delta_count_last)
    cv2.putText(a, message, (5, 30), cv2.FONT_HERSHEY_PLAIN, 1.0, (255,255,255))

    # write to window
    cv2.imshow(window_name, a)

    # refresh the display 
    key = cv2.waitKey(1) & 0xFF
    if key == 27: # Escape key
        sys.exit()

# writes opencv img to window and updates display
def showimg(window_name, a):
    cv2.imshow(window_name, a)
    key = cv2.waitKey(1)

def showcaffe(signal_name, caffe_array):
    # convert caffe format to Row,Col,RGB array for visualizing
    vis = deprocess(net, caffe_array)
    vis = vis * (255.0 / np.percentile(vis, 100.0))
    showarray(signal_name,vis)
    return vis

# a couple of utility functions for converting to and from Caffe's input image layout
def preprocess(net, img):
    #print np.float32(img).shape
    return np.float32(np.rollaxis(img, 2)[::-1]) - net.transformer.mean['data']

def deprocess(net, img):
    return np.dstack((img + net.transformer.mean['data'])[::-1])

def objective_L2(dst):
    dst.diff[:] = dst.data



# -------
# motion detector utility functions
# ------- 
def delta_images(t0, t1, t2):
    d1 = cv2.absdiff(t2, t0)
    return d1
    

# -------
# implements forward and backward passes thru the network
# apply normalized ascent step upon the image in the networks data blob
# ------- 
def make_step(net, step_size=1.5, end='inception_4c/output',jitter=32, clip=True):
    src = net.blobs['data']     # input image is stored in Net's 'data' blob
    dst = net.blobs[end]        # destination is the end layer specified by argument

    ox, oy = np.random.randint(-jitter, jitter + 1, 2)          # calculate jitter
    src.data[0] = np.roll(np.roll(src.data[0], ox, -1), oy, -2) # apply jitter shift

    # this bit is where the neural net runs the computation

    net.forward(end=end)    # make sure we stop on the chosen neural layer
    dst.diff[:] = dst.data  # specify the optimization objective
    net.backward(start=end) # backwards propagation
    g = src.diff[0]         # store the error 

    # apply normalized ascent step to the input image and get closer to our target state
    src.data[:] += step_size / np.abs(g).mean() * g

    # unshift image jitter              
    src.data[0] = np.roll(np.roll(src.data[0], -ox, -1), -oy, -2)   

    # subtract image mean and clip our matrix to the values
    bias = net.transformer.mean['data']
    src.data[:] = np.clip(src.data, -bias, 255-bias)

# -------
# sets up image buffers and octave structure for iterating thru and amplifying neural output
# iterates ththru the neural network 
# REM sleep, in other words
# ------- 
def deepdream(net, base_img, iter_n=10, octave_n=4, octave_scale=1.4, end='inception_4c/output', clip=True, **step_params):

    global t_now,t_minus,t_plus,delta_count_last,record_video_state,cap

    record_video_state = False # motion detect flag
    src = net.blobs['data']

    octaves = [preprocess(net, base_img)]
    for i in xrange(octave_n - 1):
        octaves.append(nd.zoom(octaves[-1], (1, 1.0 / octave_scale, 1.0 / octave_scale), order=1))
    detail = np.zeros_like(octaves[-1])

    # REM cycle on octaves
    for octave, octave_base in enumerate(octaves[::-1]):
        h, w = octave_base.shape[-2:]
        if octave > 0:
            h1, w1 = detail.shape[-2:]
            detail = nd.zoom(detail, (1, 1.0 * h / h1, 1.0 * w / w1), order=0)

        src.reshape(1,3,h,w)
        src.data[0] = octave_base + detail

        # iterate on current octave
        for i in xrange(iter_n):
            # motion detect
            delta_view = delta_images(t_minus, t_now, t_plus)
            retval, delta_view = cv2.threshold(delta_view, 16, 255, 3)
            cv2.normalize(delta_view, delta_view, 0, 255, cv2.NORM_MINMAX)
            img_count_view = cv2.cvtColor(delta_view, cv2.COLOR_RGB2GRAY)
            delta_count = cv2.countNonZero(img_count_view)
            delta_view = cv2.flip(delta_view, 1)

            print '[deepdream] last:{} current:{} threshold:{} size:{} percent:{}'.format(delta_count_last, delta_count, DELTA_COUNT_THRESHOLD, cap_w * cap_h, 100.0 * DELTA_COUNT_THRESHOLD/(cap_w * cap_h)  )

            if (delta_count_last < DELTA_COUNT_THRESHOLD and delta_count >= DELTA_COUNT_THRESHOLD):
                record_video_state = True
                print "+ MOVEMENT DETECTED"


            delta_count_last = delta_count

            # move images through the motion detect queue.
            t_minus = t_now
            t_now = t_plus
            t_plus = cap.read()[1]
            t_plus = cv2.blur(t_plus,(8,8))
            t_plus = cv2.resize(t_plus, (cap_w, cap_h))

            if record_video_state == True:
                print '+ TERMINATE OCTAVE LOOP'
                break

            # calls the neural net step function
            make_step(net, end=end, clip=clip, **step_params)

            # output
            showcaffe('new',src.data[0])
            #print '[deepdream] octave:{:3} iteration:{:3} end:{:} shape:{:<10}'.format(octave, i, end, src.data[0].shape)


        # extract details produced on the current octave
        detail = src.data[0] - octave_base

    # return the resulting image (converted back to x,y,RGB structured matrix)
    if record_video_state:
        print '[deepdream] return new camera img from loopreset'
        return cap.read()[1]
    else:
        print '[deepdream] return RGB from net blob'
        #return cap.read()[1]
        return deprocess(net, src.data[0])


# -------
# MAIN
# ------- 
def main(iterations, stepsize, octaves, octave_scale, end):
    global net

    # start timer
    print '+ TIMER START :REM.main'
    now = time.time()

    # set GPU mode
    caffe.set_device(0)
    caffe.set_mode_gpu()

    cv2.startWindowThread()
    cv2.namedWindow('new',cv2.WINDOW_AUTOSIZE)
    #cv2.namedWindow('input',cv2.WINDOW_AUTOSIZE)
    #cv2.namedWindow('deltaview',cv2.WINDOW_AUTOSIZE)

    # parameters
    model_path = 'E:/Users/Gary/Documents/code/models/bvlc_googlenet/'
    net_fn = model_path + 'deploy.prototxt'
    param_fn = model_path + 'bvlc_googlenet.caffemodel'

    nrframes = 1
    jitter = int(cap_w/2)
    zoom = 1

    if iterations is None: iterations = 5
    if stepsize is None: stepsize = 4
    if octaves is None: octaves = 4
    if octave_scale is None: octave_scale = 1.6
    if end is None: end = 'inception_4b/5x5'

    print '[main] iterations:{arg1} step size:{arg2} octaves:{arg3} octave_scale:{arg4} end:{arg5}'.format(arg1=iterations,arg2=stepsize,arg3=octaves,arg4=octave_scale,arg5=end)

    # Patching model to be able to compute gradients.
    model = caffe.io.caffe_pb2.NetParameter()       # load the empty protobuf model
    text_format.Merge(open(net_fn).read(), model)   # load the prototxt and place it in the empty model
    model.force_backward = True                     # add the force backward: true value
    open('tmp.prototxt', 'w').write(str(model))     # save it to a new file called tmp.prototxt

    # the neural network model
    net = caffe.Classifier('tmp.prototxt', param_fn,
        mean = np.float32([104.0, 116.0, 122.0]),   # ImageNet mean, training set dependent
        channel_swap = (2,1,0))                     # the caffe reference model has chanels in BGR instead of RGB

    frame = cap.read()[1] # initial camera image for init
    s = 0.05 # scale coefficient for uninterrupted dreaming
    while True:
        # zoom in a bit on the frame
        frame = frame*(255.0/np.percentile(cap.read()[1], 98))
        frame = nd.affine_transform(frame, [1-s,1-s,1], [cap_h*s/2,cap_w*s/2,0], order=1)

        showarray('new',frame)

        # a bit later
        later = time.time()
        difference = int(later - now)

        # a bit later
        later = time.time()
        difference = int(later - now)
        print '+ ELAPSED: {}s :{}'.format(difference,'start REM cycle')

        # kicks off rem sleep - will begin continual iteration of the image through the model
        frame = deepdream(net, frame, iter_n = iterations, octave_n = octaves, octave_scale = octave_scale, step_size = stepsize, end = end)

        # a bit later
        later = time.time()
        difference = int(later - now)
        print '+ ELAPSED: {}s :{}'.format(difference,'finish REM cycle')



# ------- 
# INIT
# ------- 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='REM')
    parser.add_argument(
        '-e','--end',
        required=False,
        help='End layer. Default: inception_4c/output')
    parser.add_argument(
        '-oct','--octaves',
        type=int,
        required=False,
        help='Octaves. Default: 4')
    parser.add_argument(
        '-octs','--octavescale',
        type=float,
        required=False,
        help='Octave Scale. Default: 1.4',)
    parser.add_argument(
        '-i','--iterations',
        type=int,
        required=False,
        help='Iterations. Default: 10')
    parser.add_argument(
        '-s','--stepsize',
        type=float,
        required=False,
        help='Step Size. Default: 1.5')
    parser.add_argument(
        '-c','--clip',
        type=float,
        required=False,
        help='Step Size. Default: 1.5')
    args = parser.parse_args()
    main(args.iterations, args.stepsize, args.octaves,  args.octavescale, args.end)
