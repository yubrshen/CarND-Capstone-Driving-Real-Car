#!/usr/bin/env python
import sys                      # for redirect stderr
import rospy

import copy                     # for deepcopy
import numpy as np              # for polyfit and poly1d

from geometry_msgs.msg import PoseStamped
from styx_msgs.msg import Lane, Waypoint

import math

'''
This node will publish waypoints from the car's current position to some `x` distance ahead.

As mentioned in the doc, you should ideally first implement a version which does not care
about traffic lights or obstacles.

Once you have created dbw_node, you will update this node to use the status of traffic lights too.

Please note that our simulator also provides the exact location of traffic lights and their
current status in `/vehicle/traffic_lights` message. You can use this message to build this node
as well as to verify your TL classifier.

TODO (for Yousuf and Aaron): Stopline location for each traffic light.
'''

LOOKAHEAD_WPS = 30 # 200 # Number of waypoints we will publish. You can change this number
LOOKAHEAD_TIME_THRESHOLD = 4 # seconds, change from 5 to 4
SAEF_TURNING_SPEED = 3.0       # meters/second

DANGER_TURNING_ANGLE = math.pi/4  # 30 degree
MPH_to_MPS = 1609.344/3600.0 # 1 mile = 1609.344 1 hour = 3600 seconds

import tf                       # This is of ROS geometry, not of TensorFlow!
def get_yaw(orientation):
    """
    Compute yaw from orientation, which is in Quaternion.
    """
    # orientation = msg.pose.orientation
    euler = tf.transformations.euler_from_quaternion([
        orientation.x,
        orientation.y,
        orientation.z,
        orientation.w])
    yaw = euler[2]
    return yaw
def to_local_coordinates(local_origin_x, local_origin_y, rotation, x, y):
    """
    compute the local coordinates for the global x, y coordinates values,
    given the local_origin_x, local_origin_y, and the rotation of the local x-axis.
    Assume the rotation is radius
    """
    shift_x = x - local_origin_x
    shift_y = y - local_origin_y

    cos_rotation = math.cos(rotation)
    sin_rotation = math.sin(rotation)

    local_x =  cos_rotation*shift_x + sin_rotation*shift_y
    local_y = -sin_rotation*shift_x + cos_rotation*shift_y  # according to John Chen's
    # assuming the orientation angle clockwise being positive
    return local_x, local_y
def publish_Lane(publisher, waypoints):
        lane = Lane()
        lane.header.frame_id = '/world'
        lane.header.stamp = rospy.Time(0)
        lane.waypoints = waypoints
        publisher.publish(lane)
def distance_two_indices(waypoints, i, j):
  a = waypoints[i].pose.pose.position
  b = waypoints[j].pose.pose.position
  return math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2  + (a.z-b.z)**2)

class WaypointUpdater(object):
    def __init__(self):
        # f = open("~/.ros/log/stderr.log", "w+") # not working here
        # self.original_stderr = sys.stderr
        # sys.stderr = f
        self.stopped = False
        rospy.init_node('waypoint_updater')
        self.max_vel_mps = rospy.get_param('waypoint_loader/velocity')*MPH_to_MPS
        rospy.loginfo('max_vel_mps: %f' % self.max_vel_mps)
        self.loop_freq = rospy.get_param('~loop_freq', 2)
        # the frequency to process vehicle messages

        rospy.Subscriber('/current_pose', PoseStamped, self.pose_cb, queue_size=1)
        self.subscriber_waypoints = rospy.Subscriber('/base_waypoints', Lane, self.waypoints_cb, queue_size=1)

        # TODO: Add a subscriber for /traffic_waypoint and /obstacle_waypoint below


        self.final_waypoints_pub = rospy.Publisher('final_waypoints', Lane, queue_size=1)

        # TODO: Add other member variables you need below

        self.base_waypoints = None  # indicating the base_waypoints is not yet available
        self.pose = None            # indicating that there is no message to process

        self.last_closest_front_waypoint_index = 0

        self.loop()
        #rospy.spin()

    import math
    
    def loop(self):
        rate = rospy.Rate(self.loop_freq)
        while not rospy.is_shutdown():
            if self.base_waypoints and self.pose:
                current_pose = self.pose.pose.position
                current_orientation = self.pose.pose.orientation
                yaw = get_yaw(current_orientation)
                
                # Compute the waypoints ahead of the current_pose
                
                local_x = -1
                i = self.last_closest_front_waypoint_index - 1
                while ((i < self.base_waypoints_num-1) and (local_x <= 0)):
                  i = (i + 1) # % self.base_waypoints_num
                  waypoint = self.base_waypoints[i]
                  w_pos = waypoint.pose.pose.position
                  local_x, local_y = to_local_coordinates(current_pose.x, current_pose.y, yaw,
                                                          w_pos.x, w_pos.y)
                # end of while (local_x < 0)
                
                # if (i == self.last_closest_front_waypoint_index):  # no more progress
                #    self.stopped = True
                # end of if (i == self.last_closest_front_waypoint_index)
                
                # now i is the index of the closest waypoint in front
                self.last_closest_front_waypoint_index = i
                
                waypoints_count = 0
                lookahead_dist = 0  # the accumulated distance of the looking ahead
                lookahead_time = 0  # the lookahead time
                
                final_waypoints = []
                accumulated_turning = 0
                # modulize the code to be less dependent
                j = self.last_closest_front_waypoint_index
                while (# (lookahead_time < LOOKAHEAD_TIME_THRESHOLD) and
                        not self.stopped and
                        (waypoints_count < LOOKAHEAD_WPS) and
                        (j < self.base_waypoints_num)):
                  waypoint = copy.deepcopy(self.base_waypoints[j])
                  j = (j + 1) # % self.base_waypoints_num
                  waypoints_count += 1
                  turning_angle = math.atan2(local_y, local_x)
                  accumulated_turning = (accumulated_turning + turning_angle) / waypoints_count
                  # average accumulated turning
                
                  # estimated_vel = min(
                  #     self.max_vel_mps, SAEF_TURNING_SPEED +
                  #     #(self.max_vel_mps - SAEF_TURNING_SPEED)*math.exp(-3.5*abs(turning_angle)))
                  #     (self.max_vel_mps - SAEF_TURNING_SPEED)*math.exp(-3.9*abs(accumulated_turning)))
                
                  # waypoint.twist.twist.linear.x = estimated_vel # meter/s
                  final_waypoints.append(waypoint)
                
                  # dist_between = self.dist_to_next[(j - 1) # % self.base_waypoints_num]
                  # lookahead_dist += dist_between
                  # lookahead_time = lookahead_dist / (estimated_vel)
                
                  # prepare for the next iteration for estimating the turning angle, velocity
                  current_waypoint = waypoint.pose.pose.position
                  w_pos = self.base_waypoints[j].pose.pose.position  # the next waypoint after current_waypoint
                  yaw = yaw + turning_angle
                  local_x, local_y = to_local_coordinates(current_waypoint.x, current_waypoint.y, yaw,
                                                          w_pos.x, w_pos.y)
                # end of while (LOOKAHEAD_TIME_THRESHOLD <= lookahead_time) or (LOOKAHEAD_WPS <= waypoints_count)
                
                rospy.loginfo('Lookahead threshold reached: waypoints_count: %d; lookahead_time: %d; self.last_closest_front_waypoint_index: %d'
                              % (waypoints_count, lookahead_time, self.last_closest_front_waypoint_index))
                
                # publish to /final_waypoints, need to package final_waypoints into Lane message
                if (0 < len(final_waypoints)):
                    publish_Lane(self.final_waypoints_pub, final_waypoints)
                self.pose = None        # indicating this message has been processed
            # end of if self.base_waypoints and self.pose
            rate.sleep()
        # end of while not rospy.is_shutdow()

    
    def pose_cb(self, msg):
        # WORKING: Implement
        #
        if self.pose is None:       # ready to process message
            self.pose = msg
        # end of if self.pose is None
        # otherwise, the current message is being processed, rejected the coming message and expect to receive more updated next one.

    def constant_policy_f(self, velocity, bound):
        xs = [-bound,   0.,       bound]
        ys = [velocity, velocity, velocity]
        return np.poly1d(np.polyfit(np.array(xs), np.array(ys), 2))
    def decleration_policy_f(self, ref_vel, bound):
        xs = []
        ys = []
    
        xs.append(-bound)
        ys.append(-0.1)
    
        xs.append(0.)
        ys.append(-0.2)
    
        # 5 meters away
        xs.append(5)
        ys.append(MPH_to_MPS*.5)
    
        # 10 meters away
        xs.append(10)
        ys.append(MPH_to_MPS*5)
    
        # 16 meters away
        xs.append(16)
        ys.append(MPH_to_MPS*5)
    
        # 2 seconds away or 24 meters away, whichever longer
        xs.append(max([ref_vel*2, 24]))
        ys.append(max([ref_vel*.2, MPH_to_MPS*5]))
    
        # 4 seconds away or 45 meters away, whichever longer
        xs.append(max([ref_vel*4, 45]))
        ys.append(max([ref_vel*.3, MPH_to_MPS*6]))
    
        # 6 seconds away or 65 meters away, whichever longer
        xs.append(max([ref_vel*6, 65]))
        ys.append(max([ref_vel*.5, MPH_to_MPS*10]))
    
        # 8 seconds away, normal speed
        xs.append(max([ref_vel*8, 85]))
        ys.append(ref_vel)
    
        # at the beginning, normal speed
        xs.append(bound)
        ys.append(ref_vel)
    
        return np.poly1d(np.polyfit(np.array(xs), np.array(ys), 3))
    
    def waypoints_cb(self, msg):
        # DONE: Implement
        waypoints = msg.waypoints
        global LOOKAHEAD_WPS        # might update it
        if self.base_waypoints is None:
            # unsubscribe to the waypoint messages, no longer needed
            self.subscriber_waypoints.unregister()
            self.subscriber_waypoints = None
    
            self.base_waypoints_num = len(waypoints)
            LOOKAHEAD_WPS = min(LOOKAHEAD_WPS, self.base_waypoints_num)
    
            # process the waypoints here
            self.dist_to_here_from_start = []
            self.base_waypoints = []
            dist = 0
            dist_so_far = 0
            for i in range(self.base_waypoints_num):
                dist_so_far += dist
                self.dist_to_here_from_start.append(dist_so_far)
    
                # do a deep copy of the data, to keep the data from lose
                # just to be safe, simply do shallow copy seems still working
                # by self.base_waypoints = waypoints
                self.base_waypoints.append(copy.deepcopy(waypoints[i]))
                # distance to the next waypoint
                if (i < self.base_waypoints_num-1):
                    dist = (
                        distance_two_indices(waypoints,  # the (i+1)_th element has not been copied yet
                                             i, (i+1) % self.base_waypoints_num))
                # end of if (i < self.base_waypoints_num-1)
    
            # end of for i in range(self.base_waypoints_num - 1)
        # end of if self.base_waypoints is None
    
        # construct the velocity policy
        self.cruise_policy = self.constant_policy_f(self.max_vel_mps, LOOKAHEAD_WPS)
        self.stop_policy = self.constant_policy_f(-0.01, LOOKAHEAD_WPS)
        self.deceleration_policy = self.decleration_policy_f(self.max_vel_mps,
                                                             LOOKAHEAD_WPS)
    
        # set the deceleration when approaching the end of the track
        total_length = self.dist_to_here_from_start[self.base_waypoints_num-1]
        # the total distance from the start to finish
        for i in range(LOOKAHEAD_WPS):
            last_ith = self.base_waypoints_num - 1 - LOOKAHEAD_WPS+i
            dist_to_the_end = (total_length - self.dist_to_here_from_start[last_ith])
            expected_velocity = self.deceleration_policy(dist_to_the_end)
            self.base_waypoints[last_ith].twist.twist.linear.x = expected_velocity
        # end of for i in range(LOOKAHEAD_WPS)

    def traffic_cb(self, msg):
            # TODO: Callback for /traffic_waypoint message. Implement
            pass
    

    def obstacle_cb(self, msg):
            # TODO: Callback for /obstacle_waypoint message. We will implement it later
            pass
    

    def get_waypoint_velocity(self, waypoint):
            return waypoint.twist.twist.linear.x
    
    def set_waypoint_velocity(self, waypoints, waypoint, velocity):
            waypoints[waypoint].twist.twist.linear.x = velocity
    
    def distance(self, waypoints, wp1, wp2):
            dist = 0
            dl = lambda a, b: math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2  + (a.z-b.z)**2)
            for i in range(wp1, wp2+1):
                dist += dl(waypoints[wp1].pose.pose.position, waypoints[i].pose.pose.position)
                wp1 = i
            return dist

if __name__ == '__main__':
    try:
        WaypointUpdater()
    except rospy.ROSInterruptException:
        rospy.logerr('Could not start waypoint updater node.')
