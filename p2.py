import os
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from moviepy.editor import VideoFileClip
from enum import Enum
import project_data

#
# The Frames list and a number
# for keeping a frame count.
#
FRAMES = []
frame_number = -1

#
# Meters per pixel are used when converting from
# pixel to world space when measuring curvature and
# offset from the center of the lane.
#
METERS_PER_PIXEL_X = 3.7/700
METERS_PER_PIXEL_Y = 30/720

#
# Lane line polynomial coefficients are averaged
# over X frames
#
AVERAGE_OVER_X_FRAMES = 7

#
# Lines with less pixel will be invalidated
#
MIN_PIXELS_FOR_VALID_LINE = 3000

#
# A change of slope of this amount over the polynomial
# will invalidate the line
#
SLOPE_TOLERANCE = 1.2

#
# Perspective transform matrix and inverse
#
M = None
M_inv = None


'''
 Side enum.
 used for specifying a side of
 the lane to a line.
'''
class Side(Enum):
    LEFT = 0
    RIGHT = 1


'''
 the Frame class.

   Packages the frame number of the video along with both of the
 detected lane lines.
'''
class Frame():
    def __init__(self, number):
        self.frame_number = number
        self.left_line = None
        self.right_line = None



'''
 the Line class

  Houses the polynomial and pixel values associated with a lane line
  and provides operations on a lane line.
'''
class Line:
    def __init__(self, x_pixels, y_pixels, height, detected = False):
        self.fitx = []
        self.fity = []
        self.lane_pixels_x = x_pixels
        self.lane_pixels_y = y_pixels
        self.detected = detected

        if len(self.lane_pixels_y) > 0 and len(self.lane_pixels_x) > 0:
            #
            # fit a polynomial using numpy polyfit
            #
            self.line_coefficients = np.polyfit(self.lane_pixels_y, self.lane_pixels_x, 2)

            #
            # Generate values for plotting
            #
            self.fity = np.linspace(0, height-1, height)
            self.fitx = (self.line_coefficients[0] * self.fity ** 2) + (self.line_coefficients[1] * self.fity) + self.line_coefficients[2]

            #
            # convert our line coordinates from pixel space to world space.
            #
            fity = self.fity * METERS_PER_PIXEL_Y
            fitx = self.fitx * METERS_PER_PIXEL_X

            #
            # Get the maximum y value to calculate the radius of curvature.
            #
            maxy = np.max(fity)

            #
            # fit to the new world space coordinates and calculate curvature
            #
            world_poly = np.polyfit(fity, fitx, 2)
            self.curvature = ((1 + ((2 * world_poly[0] * maxy) + world_poly[1]) ** 2) ** float(3/2)) / abs(2 * world_poly[0])

            self.upper_slope = (2 * self.line_coefficients[0] * self.fity[0]) + self.line_coefficients[1]
            self.mid_slope = (2 * self.line_coefficients[0] * self.fity[height//2]) + self.line_coefficients[1]
            self.lower_slope = (2 * self.line_coefficients[0] * self.fity[height-1]) + self.line_coefficients[1]
        else:
            self.detected = False

    def isValid(self):
        return (self.detected == True and
                (len(self.line_coefficients) == 3) and
                (len(self.lane_pixels_x) > MIN_PIXELS_FOR_VALID_LINE) and
                (abs(self.upper_slope - self.lower_slope) < 1.2) and
                (abs(self.upper_slope < SLOPE_TOLERANCE)) and
                (abs(self.mid_slope < SLOPE_TOLERANCE)) and
                (abs(self.lower_slope < SLOPE_TOLERANCE)))


    '''
    # Used to get the lowest point of the lane line, closest to the car,
    # when measuring the offset of the center of the car to the center of
    # the lane.
    # The maximum y value is used in the
    # polynomial to calculate the x value at the bottom of the screen
    '''
    def getLowestLinePoint(self):
        y = np.max(self.fity)
        return (self.line_coefficients[0] * y ** 2) + (self.line_coefficients[1] * y) + self.line_coefficients[2]


'''
 Measures the offset of the vehicle from the
 center of the lane.
'''
def measure_offset(left_line, right_line, width):
    #
    # Get the lowest x values (bottom of screen)
    #
    rightmax = right_line.getLowestLinePoint()
    leftmax = left_line.getLowestLinePoint()

    #
    # the center of the lane is the mid point
    # between the two detected lines.
    #
    lane_center = (rightmax + leftmax) / 2
    center_screen = (width / 2)

    #
    # Convert from pixel space to world space.
    #
    offset = round((center_screen - lane_center) * METERS_PER_PIXEL_X, 2)
    return offset


'''
 Determines and returns the camera calibration matrix and distortion
 coefficients for use in undistorting images taken by a particular camera
'''
def calibrate_camera():
    camera_calibration_images_path = "camera_cal/"

    num_x_corners = 9
    num_y_corners = 6

    obj_points = []
    img_points = []

    #
    # Prepare the object points.  These are the same for each calibration image.
    # the reshaped mgrid will give us an array like:
    # array([[ 0.,  0.,  0.],
    #        [ 1.,  0.,  0.],
    #         ...
    #        [ num_x_corners-1, num_y_corners-1, 0]])
    obj_p = np.zeros((num_x_corners * num_y_corners,  3), np.float32)
    obj_p[:, :2] = np.mgrid[0:num_x_corners, 0:num_y_corners].T.reshape(-1, 2)


    images = os.listdir(camera_calibration_images_path)
    for imagefile in images:
        #
        # Read in the image file and convert to grayscale
        #
        img = mpimg.imread(camera_calibration_images_path + imagefile)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        #
        # use cv2 findChessboardCorners to get list of image corners.
        # If found, append these corners to the img_points array.
        # Note that the obj_points are the same for each new imagefile.
        #
        ret, corners = cv2.findChessboardCorners(gray, (num_x_corners, num_y_corners), None)

        if (ret == True):
            img_points.append(corners)
            obj_points.append(obj_p)

    #
    # use the img_points to pass to  opencv calibrateCamera()
    # and get the distortion coefficients and
    # camera calibration matrix to translate 2D image points.
    #
    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(obj_points, img_points, gray.shape[::-1], None, None)

    return mtx, dist



def getLastValidLines(side, count = 1):
    global frame_number
    global FRAMES

    original_count = count

    valid_lines = []

    frame_num = frame_number
    while frame_num >= 0 and count > 0:
        prev_frame = FRAMES[frame_num]
        if side is Side.LEFT:
            if prev_frame.left_line.isValid():
                valid_lines.append(prev_frame.left_line)
                count -= 1
        else:
            if prev_frame.right_line.isValid():
                valid_lines.append(prev_frame.right_line)
                count -= 1
        frame_num -= 1

    return valid_lines



'''
Returns the perspective Transform and inverse transform used for warping
images
'''
def getPerspectiveTransform(w, h):
    global M
    global M_inv
    global video_data

    if M is None:
        #
        # Source and destination points are normalized coordinates.
        # Translate to screen coordinates using the shape of the image.
        #
        src_points = np.float32(video_data['TRANSFORM_SRC_POINTS'])
        dst_points = np.float32([(src_points[0][0], 1.0), (src_points[0][0], 0.0), (src_points[3][0], 0.0), (src_points[3][0], 1.0)])

        src_points *= (w, h)
        dst_points *= (w, h)

        M = cv2.getPerspectiveTransform(src_points, dst_points)
        M_inv = cv2.getPerspectiveTransform(dst_points, src_points)

    return M, M_inv



def threshold_image(img):
    splits_y = 9
    splits_x = 20
    h, w, c = img.shape
    out_img = np.zeros(img[:, :, 0].shape)

    blur = cv2.GaussianBlur(img, (7, 7), 0)

    for i in range(splits_y):
        for j in range(splits_x):
            partial = blur[(h//splits_y) * i:(h//splits_y) * (i+1), (w//splits_x) * j: (w//splits_x) * (j+1)]
            gray_partial = cv2.cvtColor(partial, cv2.COLOR_RGB2GRAY)
            mean = np.mean(gray_partial)

            l_thresh = video_data['L_THRESHOLD']
            b_thresh = video_data['B_THRESHOLD']
            if (mean < video_data['CONTRAST_THRESHOLD']):
                l_thresh = video_data['L_THRESHOLD_LC']
                b_thresh = video_data['B_THRESHOLD_LC']

            #
            #
            # convert to LUV color space and threshold the l values.
            #
            luv = cv2.cvtColor(partial, cv2.COLOR_RGB2LUV)
            l = luv[:, :, 0]
            lbinary = np.zeros_like(l)
            lbinary[(l >= l_thresh[0]) & (l <= l_thresh[1])] = 1

            #
            # convert to LAB color space and threshold the b values.
            #
            lab = cv2.cvtColor(partial, cv2.COLOR_RGB2LAB)
            b = lab[:, :, 2]
            bbinary = np.zeros_like(b)
            bbinary[(b >= b_thresh[0]) & (b <= b_thresh[1])] = 1

            #
            # Combine the binaries and return
            #
            combined = np.zeros_like(b)
            combined[(bbinary == 1) | (lbinary == 1)] = 1

            out_img[(h//splits_y) * i:(h//splits_y) * (i+1), (w//splits_x) * j: (w//splits_x) * (j+1)] = combined

    return out_img


def warp_image(img, inverse = False):
    h, w = img.shape[:2]

    #
    # get M, the transform matrix
    #
    M, M_inv = getPerspectiveTransform(w, h)

    #
    # use cv2.warpPerspective() to warp your image.
    # If inverse if false we warp to a bird's eye view
    # If Inverse is true we warp back to perspective
    #
    matrix = (M, M_inv)[inverse == True]
    warped = cv2.warpPerspective(img, matrix, (w, h), cv2.INTER_LINEAR)

    return warped


'''
 Searches a thresholded and warped image for lane lines.
 Returns a left lane line and a right lane line if found.
'''
def find_lane_pixels(binary_warped, left_line, right_line):
    height, width = binary_warped.shape

    # Identify the x and y positions of all nonzero pixels in the image
    nonzero = binary_warped.nonzero()
    nonzeroy = np.array(nonzero[0])
    nonzerox = np.array(nonzero[1])

    left_lane_inds  = []
    right_lane_inds = []

    nwindows      = 9   # Choose the number of sliding windows
    window_margin = 75  # the width of the windows +/- margin
    poly_margin   = 50  # the margin when searching around poly
    minpix        = 75  # minimum number of pixels found to recenter window

    if (left_line is None or not left_line.isValid()) or (right_line is None or not right_line.isValid()):
        # Take a histogram of the bottom half of the image
        histogram = np.sum(binary_warped[height//2:,:], axis=0)

        # Find the peak of the left and right halves of the histogram
        # These will be the starting point for the left and right lines
        midpoint       = np.int(histogram.shape[0]//2)
        leftx_base     = np.argmax(histogram[:midpoint])
        rightx_base    = np.argmax(histogram[midpoint:]) + midpoint
        leftx_current  = leftx_base
        rightx_current = rightx_base

        # Set height of windows - based on nwindows above and image shape
        window_height = np.int(height // nwindows)

        # Step through the windows one by one
        for window in range(nwindows):
            # Identify window boundaries in x and y (and right and left)
            win_y_low = height - (window+1) * window_height
            win_y_high = height - window * window_height

            ### Find the four below boundaries of the window ###
            win_xleft_low = leftx_current - window_margin
            win_xleft_high = leftx_current + window_margin
            win_xright_low = rightx_current - window_margin
            win_xright_high = rightx_current + window_margin

            ###  Identify the nonzero pixels in x and y within the window ###
            good_left_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) & (nonzerox >= win_xleft_low) & (nonzerox < win_xleft_high)).nonzero()[0]
            good_right_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) & (nonzerox >= win_xright_low) & (nonzerox < win_xright_high)).nonzero()[0]

            # Append these indices to the lists
            left_lane_inds.append(good_left_inds)
            right_lane_inds.append(good_right_inds)

            if (len(good_left_inds) >= minpix):
                avg_index = np.int(np.mean(nonzerox[good_left_inds]))
                leftx_current = avg_index

            if (len(good_right_inds) >= minpix):
                avg_index = np.int(np.mean(nonzerox[good_right_inds]))
                rightx_current = avg_index

        # Concatenate the arrays of indices (previously was a list of lists of pixels)
        left_lane_inds = np.concatenate(left_lane_inds)
        right_lane_inds = np.concatenate(right_lane_inds)
    else:
        #
        # We have valid lines from a previous frame.  We can search around the
        # polynomial for line pixels.
        #
        left_poly = left_line.line_coefficients
        right_poly = right_line.line_coefficients
        left_lane_inds = ((nonzerox > (left_poly[0]*(nonzeroy**2) + left_poly[1]*nonzeroy + left_poly[2] - poly_margin)) &
                          (nonzerox < (left_poly[0]*(nonzeroy**2) + left_poly[1]*nonzeroy + left_poly[2] + poly_margin)))
        right_lane_inds = ((nonzerox > (right_poly[0]*(nonzeroy**2) + right_poly[1]*nonzeroy + right_poly[2] - poly_margin)) &
                           (nonzerox < (right_poly[0]*(nonzeroy**2) + right_poly[1]*nonzeroy + right_poly[2] + poly_margin)))


    # Extract left and right line pixel positions
    leftx = nonzerox[left_lane_inds]
    lefty = nonzeroy[left_lane_inds]
    rightx = nonzerox[right_lane_inds]
    righty = nonzeroy[right_lane_inds]


    # Our new lines.
    new_left_line = Line(leftx, lefty, height, True)
    new_right_line = Line(rightx, righty, height, True)

    left_fitx = new_left_line.fitx
    right_fitx = new_right_line.fitx
    ploty = np.linspace(0, height-1, height)

    #
    # validate lines.  Make sure they don't cross each other.
    #
    if new_left_line.isValid() and new_right_line.isValid() and np.min(np.absolute(right_fitx - left_fitx)) < 300:
        new_left_line.detected = False
        new_right_line.detected = False

    return new_left_line, new_right_line


def region_of_interest(img, vertices):
    """
    Applies an image mask.

    Only keeps the region of the image defined by the polygon
    formed from `vertices`. The rest of the image is set to black.
    `vertices` should be a numpy array of integer points.
    """
    #defining a blank mask to start with
    mask = np.zeros_like(img)

    #defining a 3 channel or 1 channel color to fill the mask with depending on the input image
    if len(img.shape) > 2:
        channel_count = img.shape[2]  # i.e. 3 or 4 depending on your image
        ignore_mask_color = (255,) * channel_count
    else:
        ignore_mask_color = 255

    #filling pixels inside the polygon defined by "vertices" with the fill color
    verts = np.array([vertices], dtype=np.int32)
    cv2.fillPoly(mask, verts, ignore_mask_color)

    #returning the image only where mask pixels are nonzero
    masked_image = cv2.bitwise_and(img, mask)
    return masked_image


def fillLane(avg_left, avg_right, undist, warped):

    #
    # find our pixels to shade
    #
    width, height, _ = undist.shape
    fity = np.linspace(0, height-1, height)
    left_fitx = (avg_left[0] * fity ** 2) + (avg_left[1] * fity) + avg_left[2]
    right_fitx = (avg_right[0] * fity ** 2) + (avg_right[1] * fity) + avg_right[2]

    #
    # transpose and prepare for fillpoly
    #
    left_transpose = np.transpose(np.vstack([left_fitx, fity]))
    right_transpose = np.transpose(np.vstack([right_fitx, fity]))

    left_pts = np.array([left_transpose])
    right_pts = np.array([np.flipud(right_transpose)])
    points =  np.hstack((left_pts, right_pts))

    warp_zero = np.zeros_like(warped).astype(np.uint8)
    color_warp = np.dstack((warp_zero, warp_zero, warp_zero))

    #
    # Draw the lane onto the warped blank image
    #
    cv2.fillPoly(color_warp, np.int_([points]), (0, 255, 0))

    #
    # Warp the blank back to original image space using inverse perspective matrix (Minv)
    #
    newwarp = warp_image(color_warp, True)

    #
    # Combine the result with the original image
    #
    result = cv2.addWeighted(undist, 1, newwarp, 0.3, 0)
    return result


'''
Callback function to process a frame of video.
The given frame is first undistored and warped to a bird's-eye view.
Then lane lines are detected and the area between the lines if filled
with a translucent green.
'''
def process_frame(frame):
    global video_data
    global mtx
    global dist
    global M
    global M_inv
    global frame_number
    global FRAMES

    frame_number += 1

    #
    # Undistort the image using the camera matrix and
    # distortion coefficients.
    #
    undist = cv2.undistort(frame, mtx, dist, None, mtx)
    h, w, _ = undist.shape

    #
    # threshold color values.
    #
    thresholded = threshold_image(undist)

    #
    # Mask the region of interest
    #
    points = np.array(video_data['ROI_POINTS']) * (w, h)
    roi = region_of_interest(thresholded, points)

    #
    # Warp the image to a bird's eye view
    #
    warped = warp_image(roi)

    #
    # Create the Frame object to hold the data for the lane lines
    #
    frame = Frame(frame_number)
    prev_left_line = None
    prev_right_line = None

    if (frame_number > 0):
        prev_left_line = FRAMES[frame_number-1].left_line
        prev_right_line = FRAMES[frame_number-1].right_line

    frame.left_line, frame.right_line = find_lane_pixels(warped, prev_left_line, prev_right_line)
    FRAMES.append(frame)

    #
    # If lanes were not found or not valid we use the previous lines.
    #
    current_left_line = frame.left_line
    current_right_line = frame.right_line
    if not current_left_line.isValid():
        current_left_line = getLastValidLines(Side.LEFT, 1)[0]

    if not current_right_line.isValid():
        current_right_line = getLastValidLines(Side.RIGHT, 1)[0]


    #
    # Calculate the average left and right lines
    #
    valid_left_lines  = getLastValidLines(Side.LEFT,  AVERAGE_OVER_X_FRAMES)
    valid_right_lines = getLastValidLines(Side.RIGHT, AVERAGE_OVER_X_FRAMES)

    avg_left_coeffs = []
    [avg_left_coeffs.append(line.line_coefficients) for line in valid_left_lines]
    avg_left = np.mean(avg_left_coeffs, axis = 0)

    avg_right_coeffs = []
    [avg_right_coeffs.append(line.line_coefficients) for line in valid_right_lines]
    avg_right = np.mean(avg_right_coeffs, axis = 0)

    #
    # Use the average of the lines to fill the lane with
    # a translucent green.
    #
    out_img = fillLane(avg_left, avg_right, undist, warped)

    #
    # Measure Curvature.  Take the average of the left and right lines
    #
    avg_curve = []
    [avg_curve.append(line.curvature) for line in valid_left_lines]
    [avg_curve.append(line.curvature) for line in valid_right_lines]
    average_line_curvature = int(np.mean(avg_curve))

    #
    # S C R E E N   T E X T
    #
    avgText = "Curvature: " + str(average_line_curvature) + "m"
    cv2.putText(out_img, avgText, (100, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

    offset = measure_offset(current_left_line, current_right_line, w)
    offsetText = str(abs(offset)) + ("m left", "m right")[offset > 0] + " of center"
    cv2.putText(out_img, offsetText, (100, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

    return out_img



print("Calibrating Camera....")
mtx, dist = calibrate_camera()
print("Done.")

#video_input  = 'project_video.mp4'
video_input  = 'challenge_video.mp4'
#video_input  = 'harder_challenge_video.mp4'
video_output = 'myvideo.mp4'
video_data = project_data.getVideoData(video_input)

clip2 = VideoFileClip(video_input) #.subclip(36, 45)
video_clip = clip2.fl_image(process_frame)
video_clip.write_videofile(video_output, audio=False)
