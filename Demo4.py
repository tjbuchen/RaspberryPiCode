#!/usr/bin/env python

"""
Majority of this Code is written by Claude Pageau and the majority of credit goes to him.
I have retrofitted his Pipan face track code to work with a Pimoroni Pan Tilt HAT
Everything is elegantly commented and much information can be gleaned by logically going through the code
For a Raspberry Pi 4 Model B the best results I get is through a 320 x 200 Video Capture size
"""
import os
PROG_NAME = os.path.basename(__file__)
PROG_VER = "ver 0.95"
print("===================================")
print("%s %s using python2 and OpenCV2" % (PROG_NAME, PROG_VER))
print("Loading Libraries  Please Wait ....")
# import the necessary python libraries
import io
import time
from threading import Thread
import cv2
from picamera.array import PiRGBArray
from picamera import PiCamera
from pantilthat import *

pan(-50)
tilt(90)

# Find the full path of this python script
SCRIPT_PATH = os.path.abspath(__file__)
# get the path location only (excluding script name)
SCRIPT_DIR = SCRIPT_PATH[0:SCRIPT_PATH.rfind("/")+1]
baseFileName = SCRIPT_PATH[SCRIPT_PATH.rfind("/")+1:SCRIPT_PATH.rfind(".")]
# Read Configuration variables from config.py file
configFilePath = SCRIPT_DIR + "config.py"
if not os.path.exists(configFilePath):
    print("ERROR - Missing config.py file - Could not find Configuration file %s"
          % (configFilePath))
    import urllib2
    config_url = "https://raw.github.com/pageauc/face-track-demo/master/config.py"
    print("   Attempting to Download config.py file from %s" % config_url)
    try:
        wgetfile = urllib2.urlopen(config_url)
    except:
        print("ERROR - Download of config.py Failed")
        print("        Try Rerunning the face-track-install.sh Again.")
        print("        or")
        print("        Perform GitHub curl install per Readme.md")
        print("        and Try Again")
        print("Exiting %s" % PROG_NAME)
        quit()
    f = open('config.py', 'wb')
    f.write(wgetfile.read())
    f.close()
from config import *



# Load the BCM V4l2 driver for /dev/video0
os.system('sudo modprobe bcm2835-v4l2')
# Set the framerate ( not sure this does anything! )
os.system('v4l2-ctl -p 8')

# Initialize pipan driver  My Servo Controller is a Dagu mega
# Create Calculated Variables
cam_cx = int(CAMERA_WIDTH/2)
cam_cy = int(CAMERA_HEIGHT/2)
big_w = int(CAMERA_WIDTH * WINDOW_BIGGER)
big_h = int(CAMERA_HEIGHT * WINDOW_BIGGER)

# Setup haar_cascade variables
face_cascade = cv2.CascadeClassifier(fface1_haar_path)
frontalface = cv2.CascadeClassifier(fface2_haar_path)
profileface = cv2.CascadeClassifier(pface1_haar_path)

# Color data for OpenCV Markings
blue = (255, 0, 0)
green = (0, 255, 0)
red = (0, 0, 255)

#------------------------------------------------------------------------------
class PiVideoStream:
    def __init__(self, resolution=(CAMERA_WIDTH, CAMERA_HEIGHT),
                 framerate=CAMERA_FRAMERATE, rotation=0,
                 hflip=False, vflip=False):
        # initialize the camera and stream
        self.camera = PiCamera()
        self.camera.resolution = resolution
        self.camera.rotation = rotation
        self.camera.framerate = framerate
        self.camera.hflip = hflip
        self.camera.vflip = vflip
        self.rawCapture = PiRGBArray(self.camera, size=resolution)
        self.stream = self.camera.capture_continuous(self.rawCapture,
                                                     format="bgr",
                                                     use_video_port=True)
        # initialize the frame and the variable used to indicate
        # if the thread should be stopped
        self.frame = None
        self.stopped = False

    def start(self):
        """ start the thread to read frames from the video stream """
        t = Thread(target=self.update, args=())
        t.daemon = True
        t.start()
        return self

    def update(self):
        """ keep looping infinitely until the thread is stopped """
        for f in self.stream:
            # grab the frame from the stream and clear the stream in
            # preparation for the next frame
            self.frame = f.array
            self.rawCapture.truncate(0)
            # if the thread indicator variable is set, stop the thread
            # and resource camera resources
            if self.stopped:
                self.stream.close()
                self.rawCapture.close()
                self.camera.close()
                return

    def read(self):
        """ return the frame most recently read """
        return self.frame

    def stop(self):
        """ indicate that the thread should be stopped """
        self.stopped = True

#------------------------------------------------------------------------------
def check_fps(start_time, fps_count):
    if debug:
        if fps_count >= FRAME_COUNTER:
            duration = float(time.time() - start_time)
            FPS = float(fps_count / duration)
            print("check_fps - Processing at %.2f fps last %i frames"
                  %(FPS, fps_count))
            fps_count = 0
            start_time = time.time()
        else:
            fps_count += 1
    return start_time, fps_count

#------------------------------------------------------------------------------
def check_timer(start_time, duration):
    if time.time() - start_time > duration:
        stop_timer = False
    else:
        stop_timer = True
    return stop_timer

#------------------------------------------------------------------------------
import time

def pan_goto(x, y):
    """ Move the pan/tilt to a specific location."""
    if x < pan_max_left:
        x = pan_max_left
    elif x > pan_max_right:
        x = pan_max_right
    pan((int(x-90)))
    time.sleep(pan_servo_delay*2)
    # give the servo's some time to move
    if y < pan_max_top:
        y = pan_max_top
    elif y > pan_max_bottom:
        y = pan_max_bottom
    tilt((int(90)))
    time.sleep(pan_servo_delay)  # give the servo's some time to move
    if verbose:
        print(("pan_goto - Moved Camera to pan_cx=%i pan_cy=%i" % (x, y)))
    return x, y

#------------------------------------------------------------------------------
def pan_search(pan_cx, pan_cy):
    pan_cx = pan_cx + pan_move_x
    if pan_cx > pan_max_right:
        pan_cx = pan_max_left
        pan_cy = pan_cy + pan_move_y
        if pan_cy > pan_max_bottom:
            pan_cy = pan_max_top
    if debug:
        print("pan_search - at pan_cx=%i pan_cy=%i"
              % (pan_cx, pan_cy))
    return pan_cx, pan_cy

#------------------------------------------------------------------------------
def motion_detect(gray_img_1, gray_img_2):
    motion_found = False
    biggest_area = MIN_AREA
    # Process images to see if there is motion
    differenceimage = cv2.absdiff(gray_img_1, gray_img_2)
    differenceimage = cv2.blur(differenceimage, (BLUR_SIZE, BLUR_SIZE))
    # Get threshold of difference image based on THRESHOLD_SENSITIVITY variable
    retval, thresholdimage = cv2.threshold(differenceimage,
                                           THRESHOLD_SENSITIVITY,
                                           255, cv2.THRESH_BINARY)
    # Get all the contours found in the thresholdimage
    try:
        thresholdimage, contours, hierarchy = cv2.findContours(thresholdimage,
                                                               cv2.RETR_EXTERNAL,
                                                               cv2.CHAIN_APPROX_SIMPLE)
    except:
        contours, hierarchy = cv2.findContours(thresholdimage,
                                               cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)
    if contours:    # Check if Motion Found
        for c in contours:
            found_area = cv2.contourArea(c) # Get area of current contour
            if found_area > biggest_area:   # Check if it has the biggest area
                biggest_area = found_area   # If bigger then update biggest_area
                (mx, my, mw, mh) = cv2.boundingRect(c)    # get motion contour data
                motion_found = True
        if motion_found:
            
            
            #I CHANGED A NEGATIVE HERE ######
            
            motion_center = (int(mx + mw/2), int(my + mh/2))
            if verbose:
                print("motion-detect - Found Motion at px cxy(%i, %i)"
                      "Area wh %ix%i=%i sq px"
                      % (int(mx + mw/2), int(my + mh/2), mw, mh, biggest_area))
        else:
            motion_center = ()
    else:
        motion_center = ()
    return motion_center

#------------------------------------------------------------------------------
def face_detect(image):
    # Look for Frontal Face
    ffaces = face_cascade.detectMultiScale(image, 1.4, 1)
    if ffaces != ():
        for f in ffaces:
            face = f
        if verbose:
            print("face_detect - Found Frontal Face using face_cascade")
    else:
        # Look for Profile Face if Frontal Face Not Found
        pfaces = profileface.detectMultiScale(image, 1.4, 1)  # This seems to work better than below
        # pfaces = profileface.detectMultiScale(image,1.3, 4,(cv2.cv.CV_HAAR_DO_CANNY_PRUNING
        #                                                   + cv2.cv.CV_HAAR_FIND_BIGGEST_OBJECT
        #                                                   + cv2.cv.CV_HAAR_DO_ROUGH_SEARCH),(80,80))
        if pfaces != ():			# Check if Profile Face Found
            for f in pfaces:  # f in pface is an array with a rectangle representing a face
                face = f
            if verbose:
                print("face_detect - Found Profile Face using profileface")
        else:
            ffaces = frontalface.detectMultiScale(image, 1.4, 1)  # This seems to work better than below
            #ffaces = frontalface.detectMultiScale(image,1.3,4,(cv2.cv.CV_HAAR_DO_CANNY_PRUNING
            #                                                  + cv2.cv.CV_HAAR_FIND_BIGGEST_OBJECT
            #                                                  + cv2.cv.CV_HAAR_DO_ROUGH_SEARCH),(60,60))
            if ffaces != ():   # Check if Frontal Face Found
                for f in ffaces:  # f in fface is an array with a rectangle representing a face
                    face = f
                if verbose:
                    print("face_detect - Found Frontal Face using frontalface")
            else:
                face = ()
    return face

#------------------------------------------------------------------------------
def face_track():
    print("Initializing Pi Camera ....")
    # Setup video stream on a processor Thread for faster speed
    vs = PiVideoStream().start()   # Initialize video stream
    vs.camera.rotation = CAMERA_ROTATION
    vs.camera.hflip = CAMERA_HFLIP
    vs.camera.vflip = CAMERA_VFLIP
    time.sleep(2.0)    # Let camera warm up
    if window_on:
        print("press q to quit opencv window display")
    else:
        print("press ctrl-c to quit SSH or terminal session")
    pan_cx = cam_cx
    pan_cy = cam_cy
    fps_counter = 0
    fps_start = time.time()
    motion_start = time.time()
    face_start = time.time()
    pan_start = time.time()
    img_frame = vs.read()
    print("Position pan/tilt to (%i, %i)" % (pan_start_x, pan_start_y))
    time.sleep(0.5)
    # Position Pan/Tilt to start position
    pan_cx, pan_cy = pan_goto(pan_start_x, pan_start_y)
    grayimage1 = cv2.cvtColor(img_frame, cv2.COLOR_BGR2GRAY)
    print("===================================")
    print("Start Tracking Motion and Faces....")
    print("")
    still_scanning = True
    while still_scanning:
        motion_found = False
        face_found = False
        Nav_LR = 0
        Nav_UD = 0
        if show_fps:
            fps_start, fps_counter = check_fps(fps_start, fps_counter)
        img_frame = vs.read()
        if check_timer(motion_start, timer_motion):
            # Search for Motion and Track
            grayimage2 = cv2.cvtColor(img_frame, cv2.COLOR_BGR2GRAY)
            motion_center = motion_detect(grayimage1, grayimage2)
            grayimage1 = grayimage2  # Reset grayimage1 for next loop
            if motion_center != ():
                motion_found = True
                cx = motion_center[0]
                cy = motion_center[1]
                if debug:
                    print("face-track - Motion At cx=%3i cy=%3i " % (cx, cy))
                Nav_LR = int((cam_cx - cx)/7)
                Nav_UD = int((cam_cy - cy)/6)
                pan_cx = pan_cx - Nav_LR
                pan_cy = pan_cy - Nav_UD
                if debug:
                    print("face-track - Pan To pan_cx=%3i pan_cy=%3i Nav_LR=%3i Nav_UD=%3i "
                          % (pan_cx, pan_cy, Nav_LR, Nav_UD))
                # pan_goto(pan_cx, pan_cy)
                pan_cx, pan_cy = pan_goto(pan_cx, pan_cy)
                
                #I have added this time sleep section
            
                #time.sleep(1)
                
                motion_start = time.time()
            else:
                face_start = time.time()
        elif check_timer(face_start, timer_face):
            # Search for Face if no motion detected for a specified time period
            face_data = face_detect(img_frame)
            if face_data != ():
                face_found = True
                (fx, fy, fw, fh) = face_data
                cx = int(fx + fw/2)
                cy = int(fy + fh/2)
                Nav_LR = int((cam_cx - cx)/7)
                Nav_UD = int((cam_cy - cy)/6)
                #I CHANGED THIS HERE And back to normal tooo ############################
                
                pan_cx = pan_cx - Nav_LR
                pan_cy = pan_cy - Nav_UD
                if debug:
                    print("face-track - Found Face at pan_cx=%3i pan_cy=%3i Nav_LR=%3i Nav_UD=%3i "
                          % (pan_cx, pan_cy, Nav_LR, Nav_UD))
                pan_cx, pan_cy = pan_goto(pan_cx, pan_cy)
                face_start = time.time()
            else:
                pan_start = time.time()
        elif check_timer(pan_start, timer_pan):
            pan_cx, pan_cy = pan_search(pan_cx, pan_cy)
            pan_cx, pan_cy = pan_goto(pan_cx, pan_cy)
            img_frame = vs.read()
            grayimage1 = cv2.cvtColor(img_frame, cv2.COLOR_BGR2GRAY)
            pan_start = time.time()
            motion_start = time.time()
        else:
            motion_start = time.time()

        if window_on:
            if face_found:
                cv2.rectangle(img_frame, (fx, fy), (fx+fw, fy+fh),
                              blue, LINE_THICKNESS)
            if motion_found:
                cv2.circle(img_frame, (cx, cy), CIRCLE_SIZE,
                           green, LINE_THICKNESS)
            # Note setting a bigger window will slow the FPS
            if WINDOW_BIGGER > 1:
                img_frame = cv2.resize(img_frame, (big_w, big_h))
            cv2.imshow('Track (Press q in Window to Quit)', img_frame)
            # Close Window if q pressed while movement status window selected
            if cv2.waitKey(1) & 0xFF == ord('q'):
                vs.stop()
                cv2.destroyAllWindows()
                print("face_track - End Motion Tracking")
                still_scanning = False

#------------------------------------------------------------------------------
if __name__ == '__main__':
    try:
        face_track()
    except KeyboardInterrupt:
        print("")
        print("User pressed Keyboard ctrl-c")
        print("%s %s - Exiting" % (PROG_NAME, PROG_VER))
