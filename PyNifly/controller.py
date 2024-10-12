"""Handles import/export of controller nodes."""
# Copyright © 2024, Bad Dog.

# TODO: Make sure flags on mesh allow animations

import os
from pathlib import Path
import logging
import traceback
import bpy
import bpy.props 
from mathutils import Matrix, Vector, Quaternion, Euler, geometry
from pynifly import *
import blender_defs as BD
from nifdefs import *
import re


ANIMATION_NAME_MARKER = "ANIM"
ANIMATION_NAME_SEP = "|"
KFP_HANDLE_OFFSET = 10


# effect_shader_control_variables = {
#         EffectShaderControlledVariable.U_Offset: [("UV Converter", "Offset U")],
#         EffectShaderControlledVariable.V_Offset: [("UV Converter", "Offset V")],
#         EffectShaderControlledVariable.U_Scale: [("UV Converter", "Scale U")],
#         EffectShaderControlledVariable.V_Scale: [("UV Converter", "Scale V")],
#         EffectShaderControlledVariable.Alpha_Transparency: (
#             ("Skyrim Shader - Effect", 'Alpha Adjust'),
#             ("FO4 Effect Shader", 'Alpha Adjust'),
#         ),
#         EffectShaderControlledVariable.Emissive_Multiple: [
#             ("Skyrim Shader - Effect", "Emission Strength"),
#             ("FO4 Effect Shader", "Emission Strength"),
#             ]
# }

# lighting_shader_control_colors = {
#     LightingShaderControlledColor.EMISSIVE: [['Skyrim Shader - TSN', 'Emission Color']],
#     LightingShaderControlledColor.SPECULAR: [['Skyrim Shader - TSN', 'Specular Color']],
# }

# lighting_shader_control_variables = {
#     LightingShaderControlledFloat.Alpha: [['Skyrim Shader - TSN', 'Alpha Mult']],
#     LightingShaderControlledFloat.Emissive_Multiple: [['Skyrim Shader - TSN', 'Emission Strength']],
#     LightingShaderControlledFloat.Glossiness: [['Skyrim Shader - TSN', 'Glossiness']],
#     LightingShaderControlledFloat.Specular_Strength: [['Skyrim Shader - TSN', 'Specular Str']],
#     LightingShaderControlledFloat.U_Offset: [['UV Converter', "Offset U"]],
#     LightingShaderControlledFloat.U_Scale: [['UV Converter', "Scale U"]],
#     LightingShaderControlledFloat.V_Offset: [['UV Converter', "Offset V"]],
#     LightingShaderControlledFloat.V_Scale: [['UV Converter', "Scale V"]],
# }

# controlvar_effect = {
#     "Offset U": EffectShaderControlledVariable.U_Offset,
#     "Offset V": EffectShaderControlledVariable.V_Offset,
#     "Scale U": EffectShaderControlledVariable.U_Scale,
#     "Scale V": EffectShaderControlledVariable.V_Scale,
#     }

# controlvar_effectshaderfloat = {
#     "Alpha Adjust": EffectShaderControlledVariable.Alpha_Transparency,
#     "Emission Strength": EffectShaderControlledVariable.Emissive_Multiple, 
#     "Offset U": EffectShaderControlledVariable.U_Offset,
#     "Offset V": EffectShaderControlledVariable.V_Offset,
#     "Scale U": EffectShaderControlledVariable.U_Scale,
#     "Scale V": EffectShaderControlledVariable.V_Scale,
# }

# controlvar_lighting = {
#     "Emission Color": LightingShaderControlledColor.EMISSIVE,
#     "Specular Color": LightingShaderControlledColor.SPECULAR,
#     "Offset U": LightingShaderControlledFloat.U_Offset,
#     "Scale U": LightingShaderControlledFloat.U_Scale,
#     "Offset V": LightingShaderControlledFloat.V_Offset,
#     "Scale V": LightingShaderControlledFloat.V_Scale,
#     'Alpha Mult': LightingShaderControlledFloat.Alpha,
#     'Emission Strength': LightingShaderControlledFloat.Emissive_Multiple,
#     'Glossiness': LightingShaderControlledFloat.Glossiness,
#     'Specular Str': LightingShaderControlledFloat.Specular_Strength,
# }

shader_nodes = {    
    "Fallout 4 MTS": "Lighting", 
    "FO4 Effect Shader": "Effect", 
    "Skyrim Shader - Effect": "Effect", 
    "Skyrim Shader - TSN": "Lighting", 
} 

class ControlledVariable:
    def __init__(self, var_list):
        self.variables = var_list

    def blend_find(self, node, socket):
        """Find the right controlled variable given blender shader node and socket."""
        for n, s, d, t, v in self.variables:
            if n == node and s == socket:
                return t, v
        return None, None
    
    def nif_find(self, game, ctltype, varid):
        for n, s, d, t, v in self.variables:
            if t == ctltype and varid == v:
                for nodename, nodetype in shader_nodes.items():
                    if nodetype == n:
                        if game == 'FO4' and 'Skyrim' not in nodename:
                            return nodename, s, d
                        if game in ['SKYRIM', 'SKYRIMSE'] and 'Skyrim' in nodename:
                            return nodename, s, d
                return n, s, d
        return None, None, None
        

controlled_vars = ControlledVariable([
    ("Alpha Threshold", "0", "outputs", BSNiAlphaPropertyTestRefController, EffectShaderControlledVariable.Alpha_Transparency),
    ("Effect", "Emission Strength", "inputs", BSEffectShaderPropertyFloatController, EffectShaderControlledVariable.Emissive_Multiple),
    ("Lighting", 'Alpha Mult', "inputs", BSLightingShaderPropertyFloatController, LightingShaderControlledFloat.Alpha),
    ("Lighting", 'Emission Strength', "inputs", BSLightingShaderPropertyFloatController, LightingShaderControlledFloat.Emissive_Multiple),
    ("Lighting", 'Glossiness', "inputs", BSLightingShaderPropertyFloatController, LightingShaderControlledFloat.Glossiness),
    ("Lighting", 'Specular Str', "inputs", BSLightingShaderPropertyFloatController, LightingShaderControlledFloat.Specular_Strength),
    ("Lighting", "Emission Color", "inputs", BSLightingShaderPropertyColorController, LightingShaderControlledColor.EMISSIVE),
    ("Lighting", "Specular Color", "inputs", BSLightingShaderPropertyColorController, LightingShaderControlledColor.SPECULAR),
    ("UV Converter", "Offset U", "inputs", BSEffectShaderPropertyFloatController, EffectShaderControlledVariable.U_Offset),
    ("UV Converter", "Offset U", "inputs", BSLightingShaderPropertyFloatController, LightingShaderControlledFloat.U_Offset),
    ("UV Converter", "Offset V", "inputs", BSEffectShaderPropertyFloatController, EffectShaderControlledVariable.V_Offset),
    ("UV Converter", "Offset V", "inputs", BSLightingShaderPropertyFloatController, LightingShaderControlledFloat.V_Offset),
    ("UV Converter", "Scale U", "inputs", BSEffectShaderPropertyFloatController, EffectShaderControlledVariable.U_Scale),
    ("UV Converter", "Scale U", "inputs", BSLightingShaderPropertyFloatController, LightingShaderControlledFloat.U_Scale),
    ("UV Converter", "Scale V", "inputs", BSEffectShaderPropertyFloatController, EffectShaderControlledVariable.V_Scale),
    ("UV Converter", "Scale V", "inputs", BSLightingShaderPropertyFloatController, LightingShaderControlledFloat.V_Scale),
])

active_animation = ""

_animation_pulldown_items = []


def sanitize_name(name:str):
    return name.replace(ANIMATION_NAME_SEP, ANIMATION_NAME_SEP*2)

def desanitize_name(name:str):
    return name.replace(ANIMATION_NAME_SEP*2, ANIMATION_NAME_SEP)

def make_action_name(animation_name=None, target_obj=None, target_elem=None):
    """
    Build an animation name suitable for applying to an action.
    """
    if not animation_name: animation_name = "-"
    an = sanitize_name(animation_name)
    tn = sanitize_name(target_obj.name)
    n = ANIMATION_NAME_SEP.join([ANIMATION_NAME_MARKER, an, tn])
    if target_elem:
        n = n + "|" + target_elem
    return n

def parse_animation_name(name):
    """
    Parse an animation name and return the parts.
    Returns (animation_name, target_obj_name, target_element).
    """
    n = desanitize_name(name)
    parts = n.split("|")
    if not parts[0] == ANIMATION_NAME_MARKER: return None
    if len(parts) < 4:
        parts.append("")
    else:
        # Remove any numbers appended by blender to disambiguate
        parts[3] = BD.nonunique_name(parts[3])
    return parts[1:]

def all_animation_actions(animation:str=""):
    """
    Iterator returning all actions that are animations.
    animation = If provided, only actions that implement the animation are returned.
    """
    marker = ANIMATION_NAME_MARKER + ANIMATION_NAME_SEP
    if animation: marker = marker + animation + ANIMATION_NAME_SEP
    noname_marker = marker + "-|"
    for act in bpy.data.actions:
        if act.name.startswith(marker) and not act.name.startswith(noname_marker):
            yield act


def current_animations(nif, refobjs:BD.ReprObjectCollection):
    """
    Find all assets that appear to be animation actions.
    Returns a dictionary: {animation_name: [action, ReprObject], ...}
    """
    matches = {}
    for act in all_animation_actions():
        anim_name, target_name, elem_name = parse_animation_name(act.name)
        if target_name in refobjs.blenderdict:
            if anim_name not in matches:
                matches[anim_name] = []
            matches[anim_name].append(
                [act, refobjs.find_nifname(nif, target_name)])
    return matches


def _animations_for_pulldown(self, context):
    """Find all animations and return them in a form suitable for a Blender pulldown."""
    _animation_pulldown_items = []
    found_names = set()
    for act in all_animation_actions():
        animname = parse_animation_name(act.name)[0]
        if animname not in found_names:
            _animation_pulldown_items.append(
                (animname, animname, "Animation"), )
            found_names.add(animname)
    return _animation_pulldown_items


def assign_action(obj, elem, act):
    """Assign the given action to the given object."""
    targ = None
    if elem == 'Shader':
        targ = obj.active_material.node_tree
    else:
        targ = obj
    if targ:
        if not targ.animation_data:
            targ.animation_data_create()
        targ.animation_data.action = act
                

def apply_animation(anim_name, ctxt=bpy.context):
    """
    Apply the named animation to the currently visible objects.
    Returns a dictionary of animation values.
    """
    res = {
        "start_time": 10000.0,
        "stop_time": -10000.0,
        "start_frame": 10000,
        "stop_frame": -10000,
        "cycle_type": CycleType.LOOP,
        "frequency": 1.0,
    }
    ctxt.scene.timeline_markers.clear()

    for act in all_animation_actions(anim_name):
        log.debug(f"Applying animation action {act.name}")
        n, objname, elemname = parse_animation_name(act.name)
        if objname in ctxt.scene.objects:
            obj = ctxt.scene.objects[objname]
            assign_action(ctxt.scene.objects[objname], elemname, act)
            res["start_time"] = min(
                res["start_time"],
                (act.curve_frame_range[0]-1)/ctxt.scene.render.fps)
            res["stop_time"] = max(
                res["stop_time"], 
                (act.curve_frame_range[1]-1)/ctxt.scene.render.fps)
            res["start_frame"] = min(res["start_frame"], int(act.curve_frame_range[0]))
            res["stop_frame"] = max(res["stop_frame"], int(act.curve_frame_range[1]))
            if (not act.use_cyclic): res["cycle_type"] = CycleType.CLAMP 

            if "pynMarkers" in act:
                for name, val in act["pynMarkers"].items():
                    if name not in ctxt.scene.timeline_markers:
                        ctxt.scene.timeline_markers.new(
                            name, frame=int(val * ctxt.scene.render.fps)+1)

    active_animation = anim_name
    return res


def curve_target(curve):
    """
    Return the curve target for the curve. The target is the bone name if any,
    otherwise ''.
    """
    if curve.data_path.startswith("pose.bones"):
        return eval(curve.data_path.split('[', 1)[1].split(']', 1)[0])
    else:
        return ''


class ControllerHandler():
    def __init__(self, parent_handler):
        self.action = None
        self.action_group = ""
        self.action_name = ""
        self.action_name_root = ""
        self.frame_end = 0
        self.frame_start = 0
        self.parent = parent_handler
        self.path_name = None
        self.animation_target = None  
        self.action_target = None # 
        self.accum_root = None

        # Single MultiTargetTransformController and ObjectPalette to use fo all controller
        # sequences in a ControllerManager
        self.cm_controller = None 
        self.cm_obj_palette = None
        
        self.controlled_objects = set()
        self.start_time = sys.float_info.max
        self.end_time = sys.float_info.min

        # Necessary context from the parent.
        self.nif = parent_handler.nif
        self.context:bpy.types.Context = parent_handler.context
        self.fps = parent_handler.context.scene.render.fps
        self.logger = logging.getLogger("pynifly")
        self.auxbones = None
        if hasattr(parent_handler, "auxbones"): 
            self.auxbones = parent_handler.auxbones
        self.nif_name = None
        if hasattr(parent_handler, "nif_name"): 
            self.nif_name = parent_handler.nif_name
        self.blender_name = None
        if hasattr(parent_handler, "blender_name"): 
            self.blender_name = parent_handler.blender_name
        self.objects_created = None
        if hasattr(parent_handler, "objects_created"):
            self.objects_created:BD.ReprObjectCollection = parent_handler.objects_created
        if hasattr(parent_handler, "objs_written"):
            self.objects_created:BD.ReprObjectCollection = parent_handler.objs_written


    def warn(self, msg):
        self.logger.warning(msg)


    def _find_target(self, nifname):
        """
        Find the blender object 
        """
        try:
            nifnode = self.nif.nodes[nifname]
            return self.objects_created.find_nifnode(nifnode).blender_obj
        except:
            return None


    def _find_nif_target(self, blendname):
        try:
            nifname = self.nif_name(blendname)
            nifnode = self.nif.nodes[nifname]
            return nifnode
        except:
            return None


    def _key_nif_to_blender(self, key0, key1, key2):
        """
        Return blender fcurve handle values for key1.

        key0 and key2 may be omitted if key1 is first or last.
        """
        frame1 = key1.time*self.fps+1
        if key2:
            frame2 = key2.time*self.fps+1
            frame_delt_r = (frame2 - frame1)
            slope_right = key1.backward/frame_delt_r
        else:
            frame_delt_r = 1
            slope_right = key1.backward

        if key0:
            frame0 = key0.time * self.fps + 1
            frame_delt_l = (frame1 - frame0)
            slope_left = key1.forward/frame_delt_l
        else:
            frame_delt_l = 1
            slope_left = key1.forward

        partial = 1/3
        handle_l = Vector((frame1 - frame_delt_l*partial, key1.value - slope_left*frame_delt_l*partial))
        handle_r = Vector((frame1 + frame_delt_r*partial, key1.value + slope_right*frame_delt_r*partial))
        
        return handle_l, handle_r


    def _point3key_nif_to_blender(self, key0, key1, key2, i):
        """
        Return blender fcurve handle values for key1.

        key0 and key2 may be omitted if key1 is first or last.
        """
        _key0 = None
        if key0:
            _key0 = NiAnimKeyFloatBuf(time=key0.time,
                                      value=key0.value[i],
                                      forward=key0.forward[i],
                                      backward=key0.backward[i],)
        _key1 = None
        if key1:
            _key1 = NiAnimKeyFloatBuf(time=key1.time,
                                      value=key1.value[i],
                                      forward=key1.forward[i],
                                      backward=key1.backward[i],)
        _key2 = None
        if key2:
            _key2 = NiAnimKeyFloatBuf(time=key2.time,
                                      value=key2.value[i],
                                      forward=key2.forward[i],
                                      backward=key2.backward[i],)

        return self._key_nif_to_blender(_key0, _key1, _key2)


    def _import_interp_controller(self, fi:NiInterpController, interp:NiInterpController):
        """Import a subclass of NiInterpController."""
        fi.import_node(self, interp)


    def _import_color_controller(self, seq:NiSequence, block:ControllerLink):
        """Import one color controller block."""
        if block.node_name in self.nif.nodes:
            target_node = self.nif.nodes[block.node_name]

            target_obj = self.objects_created.find_nifnode(target_node).blender_obj
            if not target_obj:
                self.warn(f"Target object was not imported: {block.node_name}")
                return
        else:
            self.warn(f"Target block not found in nif. Is it corrupt? ({block.node_name})")

        self.action_group = "Color Property Transforms"
        self.path_name = None
        self.action_name = f"{block.node_name}_{seq.name}"


    def _new_animation(self, anim_context):
        """
        Set up to import a new animation from the nif file.

        Nif animations can control multiple elements and multiple types of elements.
        Blender actions are associated with a single element. So it may require mulitple
        blender actions to represent a nif animation. 
        """
        try:
            self.context.scene.frame_end = 1 + int(
                (anim_context.properties.stopTime - anim_context.properties.startTime) 
                * self.fps)
        except:
            # If the animation times are set on some other block, these values may be
            # bogus.
            self.context.scene.frame_end = 0
        self.context.scene.timeline_markers.clear()
        self.animation_actions = []

        try:
            self.anim_name = anim_context.name
        except:
            self.anim_name = None
        self.action_name = ""
        self.action_group = ""
        self.path_name = ""
        self.frame_start = anim_context.properties.startTime * self.fps + 1
        self.frame_end = anim_context.properties.stopTime * self.fps + 1
        self.is_cyclic = anim_context.is_cyclic

        # if the animation context has a target, set action_target
        try:
            if (not self.action_target) and (self.action_target.type != 'ARMATURE'):
                self.action_target = self._find_target(anim_context.target.name)
            elif self.action_target and self.action_target.type == 'ARMATURE' and not self.bone_target:
                self.bone_target = self._find_target(anim_context.target.name)
        except:
            pass


    def _new_action(self, name_suffix=None):
        """
        Create a new action to represent all or part of a nif animation.
        """
        if not self.animation_target:
            self.warn("No animation target") 

        suf = name_suffix
        if suf is None:
            suf = self.action_group
        self.action_name = make_action_name(self.anim_name, self.animation_target, suf)

        if self.action_target.animation_data and self.action_target.animation_data.action \
            and self.action_target.animation_data.action.name == self.action_name:
            # If the target already has an action and it matches the one we're to create,
            # use it. We will add more fcurves to animate whatever this action wants.
            self.action = self.action_target.animation_data.action
        else:
            self.action = bpy.data.actions.new(self.action_name)
            self.action.frame_start = self.frame_start
            self.action.frame_end = self.frame_end
            self.action.use_frame_range = True
            self.action.use_cyclic = self.is_cyclic 

            # Some nifs have multiple animations with different names. Others just animate
            # various nif blocks. If there's a name, make this an asset so we can track them.
            if self.anim_name:
                self.action.use_fake_user = True
                self.action.asset_mark()
                self.animation_actions.append(self.action)
                
            self.action_target.animation_data_create()
            self.action_target.animation_data.action = self.action


    def _animate_bone(self, bone_name:str):
        """
        Set up to import the animation of a bone as part of a larger animation. 
        
        Returns TRUE if the target bone was found, FALSE otherwise.
        """
        # Armature may have had bone names converted or not. Check both ways.
        name = bone_name
        if name not in self.animation_target.data.bones:
            name = self.blender_name(name)
            if name not in self.animation_target.data.bones:
                # Some nodes are uppercase in the skeleton but not in the animations.
                # Don't know if they are ignored in game or if the game is doing
                # case-insensitive matching.
                self.warn(f"Controller target not found: {bone_name}")
                return False
            
        self.bone_target = self.animation_target.pose.bones[name]
        self.path_name = f'pose.bones["{name}"]'
        return True


    def _new_bone_anim(self, ctlr):
        """
        Set up to import the animation of a bone as part of a larger animation. 
        
        Returns TRUE if the target bone was found, FALSE otherwise.
        """
        if not self.action_target:
            self.warn("No action target in _new_bone_anim")

        if self.bone_target:
            name = self.bone_target.name
        else:
            name = self.animation_target.name
        
        self.path_name = f'pose.bones["{name}"]'
        self.animation_target = self.action_target.pose.bones[name]
        self.action_group = name


    def _new_element_action(self, anim_context, target_name, property_type, suffix):
        """
        Set up info to create an action to animate a single element (bone, shader, node).
        This may be part of a larger nif animation. The actual action isn't created until
        we load the interpolator, because for various reasons we might never get there.

        target_name is the name of the target in the nif file.
         
        Returns TRUE if the target element was found, FALSE otherwise.
        """
        try:
            # self.action_target = self._find_target(target_name)
            targ = self.objects_created.find_nifname(self.nif, target_name)
            self.animation_target = targ.blender_obj
            if property_type in ['BSEffectShaderProperty', 'BSLightingShaderProperty',
                                 'NiAlphaProperty']:
                self.action_target = targ.blender_obj.active_material.node_tree
                suffix = "Shader"
            else:
                self.action_target = targ.blender_obj
            if self.action_target:
                # self._new_action(suffix)
                return True
        except:
            pass

        self.warn(f"Target of controller not found: {target_name}")
        return False
            

    def _new_transform_action(self, ctlr):
        """
        Create a new standalone NiTransform animation.

        NiNodes that are imported into an armature have to have an action on the armature
        with a path that references the bone, and it's one action for all the bones.
        NiNodes that are imported as EMPTYs have their action on the EMPTY itself and it's
        a separate action for each EMPTY.
        """
        if self.action_target and self.action_target.type == 'ARMATURE':
            if not self.action_target.animation_data:
                self._new_animation(ctlr)
                self._new_action("Transform")
            self._new_bone_anim(ctlr)
        else:
            self._new_animation(ctlr)
            # self._new_action("Transform")
            self._new_element_action(ctlr, ctlr.target.name, "Transform")
        ctlr.import_node(self, ctlr.interpolator)


    def _new_armature_action(self, anim_context):
        """
        Create an action to animate an armature.
        
        Animating an armature means moving the bone pose positions around. It is
        represented in Blender as a single action.
        """
        self._new_action("Pose")
        self.action_group = "Object Transforms"


    def _import_controller_link(self, seq:NiSequence, block:ControllerLink):
        """
        Import one controlled block.

        Imports a single controller link (Controlled Block) within a ControllerSequence
        block. One element will be animated by this link block, but may require multiple
        fcurves.
        """
        if self.animation_target.type == 'ARMATURE':
            if not self._animate_bone(block.node_name):
                return
        else:
            if not self._new_element_action(
                seq, block.node_name, block.property_type, None):
                return

        if block.controller:
            block.controller.import_node(self, block.interpolator)
            
        if block.interpolator:
            # If there's no controller, everything is done by the interpolator.
            block.interpolator.import_node(self, None)


    def _import_text_keys(self, tk:NiTextKeyExtraData):
        for time, val in tk.keys:
            self.context.scene.timeline_markers.new(val, frame=round(time*self.fps)+1)
            for a in self.animation_actions:
                if "pynMarkers" not in a:
                    a["pynMarkers"] = {}
                a["pynMarkers"][val] = time


    # --- PUBLIC FUNCTIONS ---

    def import_controller(self, ctlr, target_object=None, target_element=None, target_bone=None):
        """
        Import the animation defined by a controller block.
        
        target_object = The blender object controlled by the animation, e.g. armature, mesh object.
        target_element = The blender object an action must be bound to, e.g. bone, material.
        """
        self.animation_target = target_object
        self.action_target = target_element
        self.bone_target = target_bone
        self._new_animation(ctlr)
        ctlr.import_node(self)


    def import_bone_animations(self, arma):
        """Load any animations associated with individual armature bones."""
        for b in arma.data.bones:
            nifbone = self._find_nif_target(b.name)
            if nifbone and nifbone.controller:
                self.import_controller(nifbone.controller, arma, arma, b)


    @classmethod
    def import_block(controller_class, controller_block, parent, 
                     target_object=None):
        """
        Import a single controller block. 

        * controller_block = block to import
        * parent = NifImporter object holding context
        * target_object = target being controlled.
        """
        importer = ControllerHandler(parent)
        importer.import_controller(controller_block, target_object=target_object)


    ### EXPORT ###

    # def _get_controlled_variable(self, activated_obj):
    #     c = self.action.fcurves[0]
    #     dp = c.data_path
    #     if not dp.endswith(".default_value"):
    #         self.warn(f"FCurve has unknown data path: {dp}")
    #         return 0
    #     if "UV Converter" not in dp:
    #         self.warn(f"NYI: Cannot handle fcurve {dp}")
    #         return 0

    #     try:
    #         target_attr = eval(repr(activated_obj) + "." + dp[:-14])
    #         return controlvar_uv[target_attr.name]
    #     except:
    #         self.warn(f"NYI: Can't handle fcurve {dp}")
    #         return 0


    def _key_blender_to_nif(self, kfp0, kfp1, kfp2):
        """
        Return nif key values for keyframe point kfp1.

        kfp0 and kfp2 may be omitted if kfp1 is first or last.
        """
        slope_right = (kfp1.handle_right[1]-kfp1.co.y) / (kfp1.handle_right[0]-kfp1.co.x)
        slope_left = (kfp1.handle_left[1]-kfp1.co.y) / (kfp1.handle_left[0]-kfp1.co.x)
        
        if kfp0:
            forward = slope_left * (kfp1.co.x-kfp0.co.x)
        else:
            forward = slope_left
        if kfp2:
            backward = slope_right * (kfp2.co.x-kfp1.co.x)
        else:
            backward = slope_right

        return forward, backward


    def _get_curve_quad_values(self, curve):
        """
        Transform a blender curve into nif keys. 
        Returns [[time, value, forward, backward]...] for each keyframe in the curve.
        """
        keys = []
        points = [None] + list(curve.keyframe_points) + [None]
        while points[1]:
            k = NiAnimKeyFloatBuf()
            k.time = (points[1].co.x-1) / self.fps
            k.value = points[1].co.y
            k.forward, k.backward = self._key_blender_to_nif(points[0], points[1], points[2])
            keys.append(k)
            points.pop(0)
        return keys


    def _export_float_curves(self, fcurves, parent_ctlr=None):
        """
        Export a float curve from the list to a NiFloatInterpolator/NiFloatData pair. 
        The curve is picked off the list.

        * Returns (group name, NiFloatInterpolator for the set of curves).
        """
        fc = fcurves.pop(0)
        keys = self._get_curve_quad_values(fc)
        fdp = NiFloatDataBuf()
        fdp.keys.interpolation = NiKeyType.QUADRATIC_KEY
        fd = NiFloatData(file=self.nif, properties=fdp, keys=keys)

        fip = NiFloatInterpolatorBuf()
        fip.dataID = fd.id
        fi = NiFloatInterpolator(file=self.nif, properties=fip, parent=parent_ctlr)
        return "", fi

    
    def _export_transform_curves(self, targetobj, curve_list):
        """
        Export a group of curves from the list to a TransformInterpolator/TransformData
        pair. A group maps to a controlled object, so each group should be one such pair.
        The curves that are used are picked off the list.
        * Returns (group name, TransformInterpolator for the set of curves).
        """
        if not curve_list: return None, None
        
        targetname = curve_target(curve_list[0])
        scene_fps = self.context.scene.render.fps
        
        loc = []
        eu = []
        quat = []
        scale = []
        timemax = -10000
        timemin = 10000
        timestep = 1/self.fps
        while curve_list and curve_target(curve_list[0]) == targetname:
            c = curve_list.pop(0)
            timemax = max(timemax, (c.range()[1]-1)/scene_fps)
            timemin = min(timemin, (c.range()[0]-1)/scene_fps)
            dp = c.data_path
            if "location" in dp:
                loc.append(c)
            elif "rotation_quaternion" in dp:
                quat.append(c)
            elif "rotation_euler" in dp:
                eu.append(c)
            elif "scale" in dp:
                scale.append(c)
            else:
                self.warn(f"Unknown curve type: {dp}")
        
        if scale:
            if not self.given_scale_warning:
                self.report({"INFO"}, f"Ignoring scale transforms--not used in Skyrim")
                self.given_scale_warning = True

        if len(loc) != 3 and len(eu) != 3 and len(quat) != 4:
            self.warn(f"No useable transforms in group {targetobj.name}/{targetname}")
            return None, None

        # tibuf = NiTransformInterpolatorBuf()
        if targetobj.type == 'ARMATURE':
            if not targetname in targetobj.data.bones:
                self.warn(f"Target bone not found in armature: {targetobj.name}/{targetname}")
                return None, None
            
            targ = targetobj.data.bones[targetname]
            if targ.parent:
                targ_xf = targ.parent.matrix_local.inverted() @ targ.matrix_local
            else:
                targ_xf = targ.matrix_local
        else:
            targ_xf = Matrix.Identity(4)

        ti = NiTransformInterpolator.New(
            file=self.nif,
            translation=targ_xf.translation[:],
            rotation=targ_xf.to_quaternion()[:],
            scale=1.0,
        )
        
        td:NiTransformData = None
        if quat:
            td = NiTransformData.New(
                file=self.nif, 
                rotation_type=NiKeyType.QUADRATIC_KEY,
                parent=ti)
        elif eu:
            td = NiTransformData.New(
                file=self.nif, 
                rotation_type=NiKeyType.XYZ_ROTATION_KEY,
                xyz_rotation_types=(NiKeyType.QUADRATIC_KEY, )*3,
                parent=ti)
        if loc:
            td = NiTransformData.New(
                file=self.nif, 
                translate_type=NiKeyType.LINEAR_KEY,
                parent=ti)

        # Lots of error-checking because the user could have done any damn thing.
        if len(quat) == 4:
            timesig = timemin
            while timesig < timemax + 0.0001:
                fr = timesig * scene_fps + 1
                tdq = Quaternion([quat[0].evaluate(fr), 
                                  quat[1].evaluate(fr), 
                                  quat[2].evaluate(fr), 
                                  quat[3].evaluate(fr)])
                kq = targ_xf.to_quaternion()  @ tdq
                td.add_qrotation_key(timesig, kq)
                timesig += timestep

        if len(loc) == 3:
            timesig = timemin
            while timesig < timemax + 0.0001:
                fr = timesig * scene_fps + 1
                kv =Vector([loc[0].evaluate(fr), 
                            loc[1].evaluate(fr), 
                            loc[2].evaluate(fr)])
                rv = kv + targ_xf.translation
                td.add_translation_key(timesig, rv)
                timesig += timestep

        if len(eu) == 3:
            td.add_xyz_rotation_keys("X", self._get_curve_quad_values(eu[0]))
            td.add_xyz_rotation_keys("Y", self._get_curve_quad_values(eu[1]))
            td.add_xyz_rotation_keys("Z", self._get_curve_quad_values(eu[2]))

        return (targetname if targetname else targetobj.name), ti
    

    def _add_controlled_object(self, obj:BD.ReprObject):
        """
        Add the object and all its children recursively to the set of controlled objects.
        """
        self.controlled_objects.add(obj)
        for child in obj.blender_obj.children:
            if child.type in ['EMPTY', 'MESH']:
                ro = self.objects_created.find_blend(child)
                if ro: self._add_controlled_object(ro)
        

    def _write_controlled_objects(self, cm:NiControllerManager):
        if len(self.controlled_objects) == 0: return

        for obj in self.controlled_objects:
            self.cm_obj_palette.add_object(obj.nifnode.name, obj.nifnode)


    # def _make_fcurve_controller(self, target:BD.ReprObject, target_node:str, in_out:str, 
    #                             target_socket:str, prior_controller=None):
    #     """
    #     Make a controller to handle the given fcurve.
    #     """
    #     ctlr = target_shader.add(
    #         next_controller=prior_controller,
    #         start_time=(self.action.curve_frame_range[0]-1)/self.fps,
    #         stop_time=(self.action.curve_frame_range[1]-1)/self.fps,
    #         target=target.nifnode,
    #         var=target_var)
    #     return ctlr
    

    def _select_controller(self, dp):
        """
        Determine the controller class and controlled variable needed for an fcurve.
        """
        if (dp.startswith("location") or dp.startswith("rotation")):
            ctlclass = NiTransformController
            return ctlclass, None
        elif dp.startswith("node"):
            fcurve_match = re.match(
                """nodes\[['"]([^]]+)['"]\].(inputs|outputs)\[['"]([^]]+)['"]\]""", dp)
            if not fcurve_match:
                raise Exception(f"Could not handle animation fcurve: {dp}")
            
            node_name, i_o, socket_name = fcurve_match.groups()
            if node_name in shader_nodes:
                node_type = shader_nodes[node_name]
            else: 
                node_type = node_name
            return controlled_vars.blend_find(node_type, socket_name)


    def _export_color_curves(self, curve_list):
        """
        Export fcurves controlling a color value. The 3 color channels are popped off the
        curve list. Returns the interpolator.
        """
        dat = NiPosData.New(self.nif, key_inerp=NiKeyType.QUADRATIC_KEY)
        fcv = (curve_list.pop[0], curve_list.pop[0], curve_list.pop[0], )

        # Have to assume all channels have the same keyframes.
        keyframes = [(None, None, None, )]
        for k1, k2, k3 in zip(fcv[0].keyframe_points, fcv[1].keyframe_points, fcv[2].keyframe_points):
            if k1.co[0] != k2.co[0] or k1.co[0] != k3.co[0]:
                raise Exception(f"Cannot handle color fcurves with mismatched keyframes")
            keyframes.append((k1, k2, k3,))
        keyframes.append((None, None, None, ))

        for i in range(1, len(keyframes)-1):
            kfr, kfg, kfb = keyframes[i]
            kfbuf = NiAnimKeyQuadTransBuf()
            kfbuf.time = (kfr.co[0]-1)/self.fps
            for j in range(0, 3):
                kfbuf.value[j] = kfr.co[1]
                kfbuf.forward[j], kfbuf.backward[j] = self._key_blender_to_nif(
                    kfp0=keyframes[i-1][j],
                    kfp1=keyframes[i][j],
                    kfp2=keyframes[i+1][j]
                )
            dat.add_key(kfbuf)

        interp = NiPoint3Interpolator.New(self.nif, data=dat)
        return "", interp


    def _export_fcurves(self, controller_class, targetobj:BD.ReprObject, fcurves):
        """
        Export fcurves off the front of the list to a interpolator/data pair. fcurves used
        are removed from the list.
        """
        if issubclass(controller_class, NiTransformController):
            return self._export_transform_curves(targetobj.blender_obj, fcurves)
        
        if (issubclass(controller_class, BSLightingShaderPropertyColorController) 
            or issubclass(controller_class, BSEffectShaderPropertyColorController)):
            return self._export_color_curves(fcurves)
        
        if (issubclass(controller_class, BSLightingShaderPropertyFloatController)
            or issubclass(controller_class, BSEffectShaderPropertyFloatController)):
            return self._export_float_curves(fcurves)


    def _export_activated_obj(self, targetobj:BD.ReprObject, targetelem, theaction):
        """
        Export a single activated object--an object with animation_data on it. 

        * targetobj = Blender object to animate

        Returns a list of controller/interpolator pairs created. May have to be more than
        one if several variables are controlled, or if both variables and color are
        controlled.
        """
        interps_created = []
        target_fc = (None, None, None)
        controller = self.cm_controller
        ctlvar = ctlvar_cur = None
        ctlclass = ctlclass_cur = None
        self.action = theaction
        fcurves = list(self.action.fcurves)
        while fcurves:
            ctlclass, ctlvar = self._select_controller(fcurves[0].data_path)
            if ((ctlclass != ctlclass_cur) or (ctlvar != ctlvar_cur)
                or (ctlclass_cur is None)):
                # New node type needed, start a new controller/interpolator pair
                grp, interp = self._export_fcurves(ctlclass, targetobj, fcurves)
                if (ctlclass != NiTransformController or not self.cm_controller):
                    controller = ctlclass.New(
                        file=self.nif,
                        flags=TimeControllerFlags(
                            cycle_type=CycleType.LOOP if self.action.use_cyclic else CycleType.CLAMP,
                        ).flags,
                        next_controller=controller,
                        start_time=(self.action.curve_frame_range[0]-1)/self.fps,
                        stop_time=(self.action.curve_frame_range[1]-1)/self.fps,
                        interpolator=interp,
                        target=targetobj.nifnode.shader,
                        var=ctlvar,
                        parent=targetobj.nifnode.shader)
                interps_created.append((controller, interp))
            ctlclass_cur = ctlclass
            ctlvar_cur = ctlvar
        return interps_created

            

    def _export_activated_obj_old(self, target:BD.ReprObject,  action, controller=None):
        """
        Export a single activated object--an object with animation_data on it.

        * target = Blender object to animate
        """
        anim_name, target_name, element = parse_animation_name(action.name)
        if element == "Shader":
            action_target = target.blender_obj.active_material.node_tree
        else:
            action_target = target.blender_obj
        self.action = action_target.animation_data.action
        if controller == None:
            if action_target.type == 'ARMATURE':
                # KF animation
                controller = self.nif.rootNode
            elif action_target.type == 'SHADER':
                # Shader animation
                controller = BSEffectShaderPropertyFloatController(
                    file=self.nif,
                    parent=target.nifnode.shader)
            else:
                self.warn(f"Unknowned activated object type: {action_target.type}")
                return
        
            cp = controller.properties.copy()
            cp.startTime = (self.action.curve_frame_range[0]-1)/self.fps
            cp.stopTime = (self.action.curve_frame_range[1]-1)/self.fps
            cp.cycleType = CycleType.CYCLE_LOOP if self.action.use_cyclic else CycleType.CYCLE_CLAMP
            cp.frequency = 1.0
            controller.properties = cp

        if action_target.type == 'ARMATURE':
            # Collect list of curves. They will be picked off in clumps until the list is empty.
            curve_list = list(self.action.fcurves)
            while curve_list:
                targname, ti = self._export_transform_curves(action_target, curve_list)
                if targname and ti:
                    controller.add_controlled_block(
                        name=self.nif.nif_name(targname),
                        interpolator=ti,
                        node_name = self.nif.nif_name(targname),
                        controller_type = "NiTransformController")
                    
        elif action_target.type == 'SHADER':
            self.warn(f"NYI: Shader controller export")

        elif action_target.type in ['EMPTY', 'MESH']:
            curve_list = list(self.action.fcurves)
            while curve_list:
                targname, ti = self._export_transform_curves(action_target, curve_list)
                if self.cm_controller:
                    mttc = self.cm_controller
                else:
                    mttc = NiMultiTargetTransformController.New(
                        file=self.nif,
                        flags=TimeControllerFlags(
                            active=True, cycle_type=controller.properties.cycleType).flags,
                        target=self.accum_root,
                    )
                if targname and ti:
                    controller.add_controlled_block(
                        name=target.nifnode.name,
                        interpolator=ti,
                        controller=mttc,
                        node_name = target.nifnode.name,
                        controller_type = "NiTransformController")
            self._add_controlled_object(target)
            

    def _set_controller_props(self, props):
        props.startTime = (self.action.curve_frame_range[0]-1)/self.fps
        props.stopTime = (self.action.curve_frame_range[1]-1)/self.fps
        props.frequency = 1.0
        props.flags = (1 << 3) | (1 << 6) | ((0 if self.action.use_cyclic else 2) << 1)
        try:
            props.cycleType = CycleType.CYCLE_LOOP if self.action.use_cyclic else CycleType.CYCLE_CLAMP
        except:
            pass


    def _export_text_keys(self, cs:NiControllerSequence):
        """
        Export any timeline markers to the given NiControllerSequence as text keys.
        """
        if len(self.context.scene.timeline_markers) == 0: return

        tked = NiTextKeyExtraData.New(file=self.nif, parent=cs)
        for tm in self.context.scene.timeline_markers:
            tked.add_key((tm.frame-1)/self.fps, tm.name)


    # def _export_shader(self, activated_obj, activated_elem, nifshape):
    #     fcurve_list = list(activated_elem.animation_data.action.fcurves)
    #     fi = self._export_float_curves(fcurve_list)

    #     fcp = BSEffectShaderPropertyFloatControllerBuf()
    #     self._set_controller_props(fcp)
    #     fcp.controlledVariable = self._get_controlled_variable(activated_elem)
    #     fcp.interpolatorID = fi.id
    #     fc = BSEffectShaderPropertyFloatController(
    #         file=self.nif, properties=fcp, parent=nifshape.shader)
    

    def _export_animations(self, anims):
        """
        Export the given named animations to the target nif.
        
        * Anims = {"anim name": [(action, obj), ..], ...}
            a dictionary of animation names to list of action/object pairs that implement
            that animation.
        """
        self.accum_root = self.nif.rootNode
        self.controlled_objects = BD.ReprObjectCollection()

        self.cm_controller = NiMultiTargetTransformController.New(
            file=self.nif, flags=108, target=self.nif.rootNode)
        
        cm = NiControllerManager.New(
            file=self.parent.nif, 
            flags=TimeControllerFlags(cycle_type=CycleType.CLAMP),
            next_controller=self.cm_controller,
            parent=self.accum_root)

        self.cm_obj_palette = NiDefaultAVObjectPalette.New(self.nif, self.nif.rootNode, parent=cm)

        for anim_name, actionlist in anims.items(): 
            vals = apply_animation(anim_name)
            cs:NiControllerSequence = NiControllerSequence.New(
                file=self.parent.nif,
                name=anim_name,
                accum_root_name=self.parent.nif.rootName,
                start_time=vals["start_time"],
                stop_time=vals["stop_time"],
                cycle_type=vals["cycle_type"],
                frequency=vals["frequency"],
                parent=cm
            )

            self._export_text_keys(cs)

            for act, reprobj in actionlist:
                # if the target is an ARMATURE, do something different
                interps = []
                try:
                    interps = self._export_activated_obj(reprobj, act)
                except:
                    log.exception(f"Could not export animation {act.name} on object {reprobj.blender_obj.name}")
                
                for ctlr, intp in interps:
                    cs.add_controlled_block(
                        name=reprobj.nifnode.name,
                        interpolator=intp,
                        controller=ctlr,
                        node_name=reprobj.nifnode.name,
                        controller_type=(ctlr.blockname 
                                         if ctlr.blockname != 'NiMultiTargetTransformController'
                                         else 'NiTransformController'),
                    )
                self.cm_obj_palette.add_object(reprobj.nifnode.name, reprobj.nifnode)

        self._write_controlled_objects(cm)


    @classmethod
    def export_animation(cls, parent_handler, arma):
        """Export one action to one animation KF file."""
        exporter = ControllerHandler(parent_handler)
        exporter.nif = parent_handler.nif

        exporter.action = arma.animation_data.action
        controller = exporter.nif.rootNode
        cp = controller.properties.copy()
        cp.startTime = (exporter.action.curve_frame_range[0]-1)/exporter.fps
        cp.stopTime = (exporter.action.curve_frame_range[1]-1)/exporter.fps
        cp.cycleType = CycleType.LOOP if exporter.action.use_cyclic else CycleType.CLAMP
        cp.frequency = 1.0
        controller.properties = cp

        # Collect list of curves. They will be picked off in clumps until the list is empty.
        curve_list = list(exporter.action.fcurves)
        while curve_list:
            targname, ti = exporter._export_transform_curves(arma, curve_list)
            if targname and ti:
                controller.add_controlled_block(
                    name=exporter.nif.nif_name(targname),
                    interpolator=ti,
                    node_name = exporter.nif.nif_name(targname),
                    controller_type = "NiTransformController")


    @classmethod
    def export_shader_controller(cls, parent_handler, activeobj:BD.ReprObject, activeelem):
        # """Export an obj that has an animated shader."""
        exporter = ControllerHandler(parent_handler)
        exporter.nif = parent_handler.nif
        # exporter._export_shader(activeobj, activeelem)
        exporter._export_activated_obj(activeobj, activeelem, activeelem.animation_data.action)


    @classmethod
    def export_named_animations(cls, parent_handler, object_dict:BD.ReprObjectCollection):
        """
        Export a ControllerManager to manage all named animations (if any). 
        Only animations controlling objects in the given list count.

        * object_dict = dictionary of objects to consider
        """
        anims = current_animations(parent_handler.nif, object_dict)
        if not anims: return
        exporter = ControllerHandler(parent_handler)
        exporter._export_animations(anims)


### Handlers for importing different types of blocks

def _import_float_data(td, importer:ControllerHandler):
    if not importer.path_name: return

    exists = False
    try:
        curve = importer.action.fcurves.new(
            importer.path_name,
            action_group=importer.action_group)
    except:
        exists = True
    if exists: return

    if td.properties.keys.interpolation == NiKeyType.QUADRATIC_KEY:
        keys = [None]
        keys.extend(td.keys)
        keys.append(None)
        while keys[1]:
            frame = keys[1].time*importer.fps+1
            kfp = curve.keyframe_points.insert(frame, keys[1].value)
            kfp.handle_left_type = "FREE"
            kfp.handle_right_type = "FREE"
            kfp.handle_left, kfp.handle_right = importer._key_nif_to_blender(keys[0], keys[1], keys[2])
            importer.start_time = min(importer.start_time, keys[1].time)
            importer.end_time = max(importer.end_time, keys[1].time)
            keys.pop(0)

NiFloatData.import_node = _import_float_data


def _import_pos_data(td:NiPosData, importer:ControllerHandler):
    if not importer.path_name: return

    if td.properties.keys.interpolation == NiKeyType.QUADRATIC_KEY:
        for i in range(0, 3):
            try:
                curve = importer.action.fcurves.new(
                    importer.path_name,
                    index=i, 
                    action_group=importer.action_group)
            except:
                break
            keys = [None]
            keys.extend(td.keys)
            keys.append(None)
            while keys[1]:
                frame = keys[1].time*importer.fps+1
                kfp = curve.keyframe_points.insert(frame, keys[1].value[i])
                kfp.handle_left_type = "FREE"
                kfp.handle_right_type = "FREE"
                kfp.handle_left, kfp.handle_right \
                    = importer._point3key_nif_to_blender(keys[0], keys[1], keys[2], i)
                importer.start_time = min(importer.start_time, keys[1].time)
                importer.end_time = max(importer.end_time, keys[1].time)
                keys.pop(0)
    else:
        importer.warn(f"NYI: NiPosData type {td.properties.keys.interpolation}")

NiPosData.import_node = _import_pos_data


def _import_transform_data(td:NiTransformData, 
                           importer:ControllerHandler, 
                           have_parent_rotation,
                           tiv,
                           tiq):
    """
    Import transform data.

    - Returns the rotation mode that must be set on the target. If this interpolator
        is using XYZ rotations, the rotation mode must be set to Euler. 
    """
    if importer.path_name:
        path_prefix = importer.path_name + "."
    else:
        path_prefix = ""
    qinv = tiq.inverted()

    targ = importer.bone_target if importer.bone_target else importer.action_target
    
    targ.rotation_mode = "QUATERNION"
    if td.properties.rotationType == NiKeyType.XYZ_ROTATION_KEY:
        targ.rotation_mode = "XYZ"
        if td.xrotations or td.yrotations or td.zrotations:
            curveX = importer.action.fcurves.new(path_prefix + "rotation_euler", index=0, action_group=importer.action_group)
            curveY = importer.action.fcurves.new(path_prefix + "rotation_euler", index=1, action_group=importer.action_group)
            curveZ = importer.action.fcurves.new(path_prefix + "rotation_euler", index=2, action_group=importer.action_group)

            if len(td.xrotations) == len(td.yrotations) and len(td.xrotations) == len(td.zrotations):
                for x, y, z in zip(td.xrotations, td.yrotations, td.zrotations):
                    # In theory the X/Y/Z dimensions do not have to have key frames at
                    # the same time signatures. But an Euler rotation needs all 3.
                    # Probably they will all line up because generating them any other
                    # way is surely hard. So hope for that and post a warning if not.
                    if not (NearEqual(x.time, y.time) and NearEqual(x.time, z.time)):
                        importer.warn(f"Keyframes do not align for '{importer.path_name}. Animations may be incorrect.")

                    # Need to apply the parent rotation. If we stay in Eulers, we may
                    # have gimbal lock. If we convert to quaternions, we may lose the
                    # distinction between +180 and -180, which are different things
                    # for animations. So only apply the parent rotation if there is
                    # one; in those cases we're just hoping it comes out right.
                    ve = Euler(Vector((x.value, y.value, z.value)), 'XYZ')
                    if have_parent_rotation:
                        ke = ve.copy()
                        kq = ke.to_quaternion()
                        vq = qinv @ kq
                        ve = vq.to_euler()
                    curveX.keyframe_points.insert(x.time * importer.fps + 1, ve[0])
                    curveY.keyframe_points.insert(y.time * importer.fps + 1, ve[1])
                    curveZ.keyframe_points.insert(z.time * importer.fps + 1, ve[2])
                    importer.start_time = min(importer.start_time, x.time, y.time, z.time)
                    importer.end_time = max(importer.end_time, x.time, y.time, z.time)
                    
            else:
                # This method of getting the inverse of the Euler doesn't always
                # work, maybe because of gimbal lock.
                ve = tiq.to_euler()

                for i, k in enumerate(td.xrotations):
                    val = k.value - ve[0]
                    curveX.keyframe_points.insert(k.time * importer.fps + 1, val)
                    importer.start_time = min(importer.start_time, k.time)
                    importer.end_time = max(importer.end_time, k.time)
                for i, k in enumerate(td.yrotations):
                    val = k.value - ve[1]
                    curveY.keyframe_points.insert(k.time * importer.fps + 1, val)
                    importer.start_time = min(importer.start_time, k.time)
                    importer.end_time = max(importer.end_time, k.time)
                for i, k in enumerate(td.zrotations):
                    val = k.value - ve[2]
                    curveZ.keyframe_points.insert(k.time * importer.fps + 1, val)
                    importer.start_time = min(importer.start_time, k.time)
                    importer.end_time = max(importer.end_time, k.time)
    
    elif td.properties.rotationType in [NiKeyType.LINEAR_KEY, NiKeyType.QUADRATIC_KEY]:
        try:
            # The curve may already have been started.
            curveW = importer.action.fcurves.new(path_prefix + "rotation_quaternion", index=0, action_group=importer.action_group)
            curveX = importer.action.fcurves.new(path_prefix + "rotation_quaternion", index=1, action_group=importer.action_group)
            curveY = importer.action.fcurves.new(path_prefix + "rotation_quaternion", index=2, action_group=importer.action_group)
            curveZ = importer.action.fcurves.new(path_prefix + "rotation_quaternion", index=3, action_group=importer.action_group)
        except:
            curveW = importer.action.fcurves[path_prefix + "rotation_quaternion"]

        for i, k in enumerate(td.qrotations):
            kq = Quaternion(k.value)
            # Auxbones animations are not correct yet, but they seem to need something
            # different from animations on the full skeleton.
            if importer.auxbones:
                vq = kq 
            else:
                vq = qinv @ kq 

            curveW.keyframe_points.insert(k.time * importer.fps + 1, vq[0])
            curveX.keyframe_points.insert(k.time * importer.fps + 1, vq[1])
            curveY.keyframe_points.insert(k.time * importer.fps + 1, vq[2])
            curveZ.keyframe_points.insert(k.time * importer.fps + 1, vq[3])
            importer.start_time = min(importer.start_time, k.time)
            importer.end_time = max(importer.end_time, k.time)

    elif td.properties.rotationType == NiKeyType.NO_INTERP:
        pass
    else:
        importer.warn(f"Not Yet Implemented: Rotation type {td.properties.rotationType} at {importer.path_name}")

    # Seems like a value of + or - infinity in the Transform
    if len(td.translations) > 0:
        curveLocX = importer.action.fcurves.new(path_prefix + "location", index=0, action_group=importer.action_group)
        curveLocY = importer.action.fcurves.new(path_prefix + "location", index=1, action_group=importer.action_group)
        curveLocZ = importer.action.fcurves.new(path_prefix + "location", index=2, action_group=importer.action_group)
        for k in td.translations:
            v = Vector(k.value)

            if importer.auxbones:
                pass 
            else:
                v = v - tiv
            curveLocX.keyframe_points.insert(k.time * importer.fps + 1, v[0])
            curveLocY.keyframe_points.insert(k.time * importer.fps + 1, v[1])
            curveLocZ.keyframe_points.insert(k.time * importer.fps + 1, v[2])
            importer.start_time = min(importer.start_time, k.time)
            importer.end_time = max(importer.end_time, k.time)

NiTransformData.import_node = _import_transform_data


# #####################################
# Importers for NiInterpolator blocks. 

def _import_float_interpolator(fi:NiFloatInterpolator, 
                               importer:ControllerHandler, 
                               interp:NiInterpController):
    """
    "interp" is the controller to use when this interpolator doesn't have one.
    """
    td = fi.data
    if td: td.import_node(importer)
    
NiFloatInterpolator.import_node = _import_float_interpolator


def _import_point3_interpolator(fi:NiPoint3Interpolator, 
                                importer:ControllerHandler, 
                                interp:NiInterpController):
    """
    "interp" is the controller to use when this interpolator doesn't have one.
    """
    td = fi.data
    if td: td.import_node(importer)
    
NiPoint3Interpolator.import_node = _import_point3_interpolator


def _import_blendfloat_interpolator(fi:NiBlendFloatInterpolator, 
                               importer:ControllerHandler, 
                               interp:NiInterpController):
    if fi.properties.flags != InterpBlendFlags.MANAGER_CONTROLLED:
        importer.warn(f"NYI: BlendFloatInterpolator that is not MANAGER_CONTROLLED")
    
NiBlendFloatInterpolator.import_node = _import_blendfloat_interpolator


def _import_transform_interpolator(ti:NiTransformInterpolator, 
                                   importer:ControllerHandler, 
                                   interp:NiInterpController):
    """
    Import a transform interpolator, including its data block.

    - Returns the rotation mode that must be set on the target. If this interpolator
        is using XYZ rotations, the rotation mode must be set to Euler. 
    """
    if not ti.data:
        # Some NiTransformController blocks have null duration and no data. Not sure
        # how to interpret those, so ignore them.
        return None
    
    importer.action_group = "Object Transforms"

    # ti, the parent NiTransformInterpolator, has the transform-to-global necessary
    # for this animation. It matches the transform of the target being animated.
    have_parent_rotation = False
    if max(ti.properties.rotation[:]) > 3e+38 or min(ti.properties.rotation[:]) < -3e+38:
        tiq = Quaternion()
    else:
        have_parent_rotation = True
        tiq = Quaternion(ti.properties.rotation)
    # qinv = tiq.inverted()
    tiv = Vector(ti.properties.translation)

    # Some interpolators have bogus translations. Dunno why.
    if tiv[0] <= -1e+30 or tiv[0] >= 1e+30: tiv[0] = 0
    if tiv[1] <= -1e+30 or tiv[1] >= 1e+30: tiv[1] = 0
    if tiv[2] <= -1e+30 or tiv[2] >= 1e+30: tiv[2] = 0

    ti.data.import_node(importer, have_parent_rotation, tiv, tiq)

NiTransformInterpolator.import_node = _import_transform_interpolator


# #####################################
# Importers for NiTimeController blocks. Controllers usually have their own interpolators,
# but may not. If not, they get the interpolator from a parent ControllerLink, so it has
# to be passed in.

def _ignore_interp(interp):
    """Determine whether to ignore an interpolator."""
    return ((not interp) 
            or (isinstance(interp, NiBlendInterpolator) 
                and interp.properties.flags == InterpBlendFlags.MANAGER_CONTROLLED))


def _import_transform_controller(tc:NiTransformController, 
                                 importer:ControllerHandler, 
                                 interp:NiInterpController=None):
    """Import transform controller block."""
    importer.action_group = "Object Transforms"
    if not interp:
        interp = tc.interpolator

    if importer.animation_target and interp:
        if importer.animation_target.type == 'ARMATURE':
            importer._animate_bone(tc.target.name)
            if not importer.action:
                importer._new_action()
        else:
            importer._new_action()
        interp.import_node(importer, None)
    else:
        importer.warn(f"Found no target for {type(tc)}")

NiTransformController.import_node = _import_transform_controller


def _import_alphatest_controller(ctlr:BSNiAlphaPropertyTestRefController, 
                                 importer:ControllerHandler,
                                 interp:NiInterpController=None):
    importer.action_group = "Shader"
    importer.path_name = f'nodes["Alpha Threshold"].outputs[0].default_value'
    if not interp:
        interp = ctlr.interpolator
    if _ignore_interp(interp):
        log.debug(f"No interpolator available for controller {ctlr.id}")
        return
    
    td = interp.data
    if td: 
        importer._new_action()
        td.import_node(importer)
    
BSNiAlphaPropertyTestRefController.import_node = _import_alphatest_controller


def _import_ESPFloat_controller(ctlr:BSEffectShaderPropertyFloatController, 
                                 importer:ControllerHandler,
                                 interp:NiInterpController=None):
    """
    Import float controller block.
    importer.action_target should be the material node_tree the action affects.
    """
    if not importer.action_target:
        importer.warn("No target object")

    importer.action_group = "Shader"
    importer.path_name = ""
    try:
        nodename, inputname, in_out = controlled_vars.nif_find(
            importer.nif.game,
            BSEffectShaderPropertyFloatController, 
            ctlr.properties.controlledVariable)
        importer.path_name = \
            f'nodes["{nodename}"].{in_out}["{inputname}"].default_value'
    except:
        pass

    if not importer.path_name: 
        raise Exception(f"NYI: Cannot handle controlled variable on controller {ctlr.id}: {repr(EffectShaderControlledVariable(ctlr.properties.controlledVariable))}") 
    else:    
        if not interp:
            interp = ctlr.interpolator
        if _ignore_interp(interp):
            log.debug(f"No interpolator available for controller {ctlr.id}")
            return
        td = interp.data
        if td: 
            importer._new_action()
            td.import_node(importer)
    
BSEffectShaderPropertyFloatController.import_node = _import_ESPFloat_controller


def _import_ESPColor_controller(ctlr:BSEffectShaderPropertyFloatController, 
                                 importer:ControllerHandler,
                                 interp:NiInterpController=None):
    """
    Import float controller block.
    importer.action_target should be the material node_tree the action affects.
    """
    if not importer.action_target:
        importer.warn("No target object")

    importer.action_group = "Shader"
    importer.path_name = ""
    importer.path_name = f'nodes["FO4 Effect Shader"].inputs["Emission Color"].default_value'

    if not interp:
        interp = ctlr.interpolator
    if _ignore_interp(interp):
        log.debug(f"No interpolator available for controller {ctlr.id}")
        return
    td = interp.data
    if td: 
        importer._new_action()
        td.import_node(importer)
    
BSEffectShaderPropertyColorController.import_node = _import_ESPColor_controller


def _import_LSPColorController(ctlr:BSLightingShaderPropertyColorController, 
                               importer:ControllerHandler,
                               interp:NiInterpController=None):
    """
    Import controller block.
    importer.action_target should be the material node_tree the action affects.
    """
    if not interp:
        interp = ctlr.interpolator
    if _ignore_interp(interp):
        # If no usable interpolator, just skip. This is part of a ControllerSequence and
        # we'll find it again when we load that.
        log.debug(f"No interpolator available for controller {ctlr.id}")
        return

    if not importer.action_target:
        importer.warn("No target object")

    importer.action_group = "Shader"
    importer.path_name = ""
    try:
        nodename, inputname, in_out = controlled_vars.nif_find(
            importer.nif.game,
            BSLightingShaderPropertyColorController, 
            ctlr.properties.controlledVariable)
        importer.path_name = \
                f'nodes["{nodename}"].{in_out}["{inputname}"].default_value'
    except:
        pass

    if not importer.path_name: 
        importer.warn(f"NYI: Cannot handle controlled variable on controller {ctlr.id}: {repr(LightingShaderControlledColor(ctlr.properties.controlledVariable))}") 
    else:    
        
        td = interp.data
        if td: 
            importer._new_action()
            td.import_node(importer)
    
BSLightingShaderPropertyColorController.import_node = _import_LSPColorController


def _import_LSPFloatController(ctlr:BSLightingShaderPropertyFloatController, 
                               importer:ControllerHandler,
                               interp:NiInterpController=None):
    """
    Import controller block.
    importer.action_target should be the material node_tree the action affects.
    """
    if not interp:
        interp = ctlr.interpolator
    if _ignore_interp(interp):
        # If no usable interpolator, just skip. This is part of a ControllerSequence and
        # we'll find it again when we load that.
        log.debug(f"No interpolator available for controller {ctlr.id}")
        return

    if not importer.action_target:
        raise Exception("No target object")

    importer.action_group = "Shader"
    importer.path_name = ""
    try:
        nodename, inputname, in_out = controlled_vars.nif_find(
            importer.nif.game,
            BSLightingShaderPropertyFloatController, 
            ctlr.properties.controlledVariable)
        importer.path_name = \
            f'nodes["{nodename}"].{in_out}["{inputname}"].default_value'
    except:
        pass

    if not importer.path_name: 
        importer.warn(f"NYI: Cannot handle controlled variable on controller {ctlr.id}: {ctlr.properties.controlledVariable} on {ctlr.id}") 
    else:    
        
        td = interp.data
        if td: 
            importer._new_action()
            td.import_node(importer)
    
BSLightingShaderPropertyFloatController.import_node = _import_LSPFloatController


def _import_multitarget_transform_controller( 
        block:ControllerLink, 
        importer:ControllerHandler, 
        interp:NiInterpController, ):
    """Import multitarget transform controller block from a controller link block."""
    # NiMultiTargetTransformController doesn't actually link to a controller or an
    # interpolator. It just references the target objects. The parent Control Link
    # block references the interpolator.
    importer.action_group = None
    importer.path_name = ""
    importer._new_action()

NiMultiTargetTransformController.import_node = _import_multitarget_transform_controller


def _import_controller_sequence(seq:NiControllerSequence, 
                                importer:ControllerHandler,
                                interp=None):
    """
    Import a single controller sequence block.
    
    A controller sequence represents a single animation. It contains a list of
    ControllerLink structures, called "Controlled Block" in NifSkope. (They are not
    full, separate blocks in the nif file.) Each Controller Link block controls one
    element being animated.

    A ControllerSequence maps to multiple Blender actions, because several objects may
    be animated. The actions are marked as assets so they persist. 

    There may be text keys associated with this animation. They are represented as
    Blender TimelineMarker objects and apply across all the different actions that
    make up the animation. They are aso stored as a dictionary on the actions so they
    can be recovered when the user switches between animations.
    """
    importer._new_animation(seq)
    importer.start_time = min(importer.start_time, seq.properties.startTime)
    importer.end_time = max(importer.end_time, seq.properties.stopTime)

    if importer.animation_target.type == 'ARMATURE':
        importer._new_armature_action(seq)

    for cb in seq.controlled_blocks:
        importer._import_controller_link(seq, cb)

    if seq.text_key_data: importer._import_text_keys(seq.text_key_data)

NiControllerSequence.import_node = _import_controller_sequence


def _import_controller_manager(cm:NiControllerManager, 
                                importer:ControllerHandler, 
                                interp=None):
    anim = None
    for seq in cm.sequences.values():
        # importer._new_controller_seq_action(seq)
        seq.import_node(importer)
        if not anim: anim = seq.name
    if anim: 
        anim_dict = apply_animation(anim)
        bpy.context.scene.frame_start = anim_dict["start_frame"]
        bpy.context.scene.frame_end= anim_dict["stop_frame"]

NiControllerManager.import_node = _import_controller_manager


class AssignAnimPanel(bpy.types.Panel):
    bl_idname = "PYNIFLY_apply_anim"
    bl_label = "Apply Animation"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw(self, context):
        self.layout.label(text="Apply Animation")


class WM_OT_ApplyAnim(bpy.types.Operator):
    bl_idname = "wm.apply_anim"
    bl_label = "Apply Animation"
    bl_options = {'REGISTER', 'UNDO'}

    # Keeping the list of animations in a module-level variable because EnumProperty doesn't
    # like it if the list contents goes away.
    _animations_found = []

    anim_chooser : bpy.props.EnumProperty(name="Animation Selection",
                                           items=_animations_for_pulldown,
                                           )  # type: ignore
    

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event): # Used for user interaction
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def draw(self, context): # Draw options (typically displayed in the tool-bar)
        row = self.layout
        row.prop(self, "anim_chooser", text="Animation name")

    def execute(self, context): # Runs by default 
        anim_dict = apply_animation(self.anim_chooser, context)
        context.scene.frame_start = anim_dict["start_frame"]
        context.scene.frame_end= anim_dict["stop_frame"]
        return {'FINISHED'}


def register():
    try:
        bpy.utils.unregister_class(WM_OT_ApplyAnim)
    except:
        pass
    bpy.utils.register_class(WM_OT_ApplyAnim)

def unregister():
    try:
        bpy.utils.unregister_class(WM_OT_ApplyAnim)
    except:
        pass
