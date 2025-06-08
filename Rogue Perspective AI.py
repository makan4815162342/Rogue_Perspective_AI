import bpy
from bpy.props import (
    PointerProperty, StringProperty, FloatProperty,
    IntProperty, BoolProperty, EnumProperty, FloatVectorProperty
)
from bpy.types import Operator, Panel, PropertyGroup
import math
from mathutils import Vector
import random
from bpy_extras.object_utils import world_to_camera_view # For camera trimming

# --- START OF FILE Rogue Perspective AI Mixed.txt ---

bl_info = {
    "name": "Rogue Perspective AI",
    "author": "Your Name & Gemini & Copilot",
    "version": (0, 4, 7), # Incremented version for this fix
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > RogueAI",
    "description": "Assists with creating perspective curve guides. (VP persistence, 1P Z-freedom, stability attempts)",
    "warning": "If crashes occur on mode switch, check console for errors.",
    "doc_url": "",
    "category": "3D View",
}

# ... (Keep all your existing Global Variables, Utility Functions, Callbacks, Properties, etc. from line 18 down to line 548)
# Global Variables / Constants
# -----------------------------------------------------------
PERSPECTIVE_HELPER_COLLECTION = "Perspective_Helpers_Collection"
PERSPECTIVE_GUIDES_COLLECTION = "Perspective_Guides_Curves_Collection"
HORIZON_CTRL_OBJ_NAME = "CTRL_Perspective_Horizon"
HORIZON_CURVE_OBJ_NAME = "VISUAL_Horizon_Line"
VP_PREFIX = "VP_"
DEFAULT_LINE_EXTENSION = 100.0

VP_TYPE_SPECIFIC_PREFIX_MAP = {
    'ONE_POINT': VP_PREFIX + "1P",
    'TWO_POINT': VP_PREFIX + "2P",
    'THREE_POINT_H': VP_PREFIX + "3P_H",
    'THREE_POINT_V': VP_PREFIX + "3P_V",
    'FISH_EYE': VP_PREFIX + "FE_Center" # Note: Used as base, often with _1 or specific name
}
previous_perspective_type_on_switch = 'NONE'

EXTRACTION_AIDS_COLLECTION = "Perspective_Extraction_Aids_Collection"

# -----------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------

# -----------------------------------------------------------
# Helper: Add Vanishing Point Empty if Missing
# -----------------------------------------------------------
# -----------------------------------------------------------
# Helper: Add Vanishing Point Empty if Missing
# -----------------------------------------------------------

def draw_finalize_guides_section(layout, context):
    ts = context.scene.perspective_tool_settings_splines
    current_type = ts.current_perspective_type

    finalize_box = layout.box()
    finalize_box.label(text="Finalize & Manage Guides:")

    # --- Merging Guides ---
    merge_box = finalize_box.box()  # Sub-box for merging
    merge_box.label(text="Merge Guide Groups:")
    if current_type != 'NONE' and current_type in PERSPECTIVE_OT_merge_specific_guides.GUIDE_GROUP_DEFS:
        merge_col = merge_box.column(align=True)
        groups = PERSPECTIVE_OT_merge_specific_guides.GUIDE_GROUP_DEFS[current_type]
        for group_id, (prefixes, suffix) in groups.items():
            display_label = suffix.replace(current_type.replace('_',''), "").replace("_Lines","").replace("_", " ").strip().title()
            if not display_label:
                display_label = group_id.replace("_LINES", "").replace("_", " ").strip().title()
            op = merge_col.operator(PERSPECTIVE_OT_merge_specific_guides.bl_idname,
                                    text=f"Merge {display_label} ({current_type.replace('_',' ')})")
            op.group_identifier = group_id
        op_all = merge_box.operator(PERSPECTIVE_OT_merge_specific_guides.bl_idname,
                                    text=f"Merge ALL {current_type.replace('_',' ').title()} Guides")
        op_all.group_identifier = "ALL_CURRENT_TYPE"
    else:
        merge_box.label(text="No specific merge groups for current mode.", icon='INFO')

    finalize_box.operator(PERSPECTIVE_OT_merge_guides.bl_idname,
                          text="Merge All Visible Guide Objects",
                          icon='OBJECT_DATAMODE')
    finalize_box.separator()

    # --- Show/Hide Guide Groups Section ---
    toggle_box = finalize_box.box()  # Sub-box for visibility
    toggle_box.label(text="Toggle Guide Group Visibility:")
    col_sh = toggle_box.column(align=True)
    if current_type != 'NONE' and current_type in PERSPECTIVE_OT_merge_specific_guides.GUIDE_GROUP_DEFS:
        groups = PERSPECTIVE_OT_merge_specific_guides.GUIDE_GROUP_DEFS[current_type]
        for group_id, (prefixes, _) in groups.items():
            if prefixes:
                label = group_id.replace("_LINES", "").replace("_", " ").strip().title()
                op_sh = col_sh.operator(PERSPECTIVE_OT_toggle_guide_visibility.bl_idname,
                                         text=f"Toggle {label}")
                op_sh.group_prefix = prefixes[0]
    else:
        col_sh.label(text="Select a perspective type for visibility toggles.", icon='INFO')


def add_vp_empty_if_missing(context, target_vp_name, default_location, empty_color=(0.8, 0.8, 0.8, 1.0)):
    vp_obj = bpy.data.objects.get(target_vp_name)
    helpers_coll = get_helpers_collection(context) 

    if not vp_obj:
        print(f"DEBUG add_vp_empty_if_missing: VP '{target_vp_name}' NOT found. Creating new.")
        vp_obj = bpy.data.objects.new(target_vp_name, None)
        vp_obj.empty_display_type = 'SPHERE' 
        vp_obj.empty_display_size = 0.35   
        vp_obj.location = default_location
        
        if vp_obj.name not in helpers_coll.objects:
            try:
                for coll in list(vp_obj.users_collection): 
                    coll.objects.unlink(vp_obj)
                helpers_coll.objects.link(vp_obj)
            except Exception as e:
                print(f"DEBUG add_vp_empty_if_missing: Error managing collections for new VP {target_vp_name}: {e}")
        print(f"DEBUG add_vp_empty_if_missing: Created and linked new VP: {target_vp_name} at {default_location}")
    else:
        print(f"DEBUG add_vp_empty_if_missing: VP '{target_vp_name}' found. Ensuring collection and color.")
        if vp_obj.name not in helpers_coll.objects:
            print(f"DEBUG add_vp_empty_if_missing: Existing VP '{target_vp_name}' not in helpers_coll. Linking.")
            for coll in list(vp_obj.users_collection):
                if coll != helpers_coll:
                    coll.objects.unlink(vp_obj)
            try:
                helpers_coll.objects.link(vp_obj)
            except RuntimeError: 
                 pass

    current_color_tuple = tuple(round(c, 4) for c in vp_obj.color)
    setting_color_tuple = tuple(round(c, 4) for c in empty_color[:4]) 

    if current_color_tuple != setting_color_tuple:
        vp_obj.color = empty_color[:4] 
        print(f"DEBUG add_vp_empty_if_missing: Updated color for VP {vp_obj.name}")
        
    return vp_obj

def refresh_extraction_aid_lines(context, from_selection_change=False):
    print(f"\n--- refresh_extraction_aid_lines CALLED (from_selection_change: {from_selection_change}) ---")
    if not hasattr(context.scene, "perspective_tool_settings_splines"):
        print("DEBUG refresh_aids: Perspective settings not found.")
        return
    ts = context.scene.perspective_tool_settings_splines
    aids_coll = get_extraction_aids_collection(context)
    
    # Always clear any existing aid lines.
    print("DEBUG refresh_aids: Clearing all existing VISUAL aid lines.")
    clear_extraction_aids_lines(context)
    
    if not ts.show_extraction_helper_lines:
        print("DEBUG refresh_aids: Toggle is OFF, no aid lines will be drawn.")
        if context.area:
            context.area.tag_redraw()
        return

    # Get all selected empties.
    selected_empties = [obj for obj in context.selected_objects if obj.type == 'EMPTY']
    
    if ts.current_perspective_type == 'ONE_POINT':
        helpers_1p = sorted([e for e in selected_empties if "1P_Aid" in e.name], key=lambda o: o.name)
        if len(helpers_1p) == 4:
            # Assume the first two helpers define one line and the next two the second line.
            e1, e2, e3, e4 = helpers_1p
            create_or_update_extraction_aid_line(context, "VISUAL_Extraction_Line_1P_A", 
                                                e1.matrix_world.translation, e2.matrix_world.translation, aids_coll)
            create_or_update_extraction_aid_line(context, "VISUAL_Extraction_Line_1P_B", 
                                                e3.matrix_world.translation, e4.matrix_world.translation, aids_coll)
            print("DEBUG refresh_aids: Drew/Updated 1P aid lines")
        else:
            print("DEBUG refresh_aids: Not exactly 4 '1P_Aid' empties selected for 1P aid lines.")


    elif ts.current_perspective_type == 'TWO_POINT':
        # ... your two-point extraction code ...
        pass

    elif ts.current_perspective_type == 'THREE_POINT':
        print("DEBUG refresh_aids: In THREE_POINT block")

        # --- Aid Lines for Horizontal VP1 (H_VP1) ---
        helpers_3p_hvp1 = sorted([e for e in selected_empties if "3P_H1_Aid" in e.name], key=lambda o: o.name)
        if len(helpers_3p_hvp1) == 4:
            print(f"DEBUG refresh_aids: Drawing 3P_H1 aid lines for: {[e.name for e in helpers_3p_hvp1]}")
            e1, e2, e3, e4 = helpers_3p_hvp1[0], helpers_3p_hvp1[1], helpers_3p_hvp1[2], helpers_3p_hvp1[3]
            create_or_update_extraction_aid_line(context, "VISUAL_Extraction_Line_3P_H1_A", 
                                                   e1.matrix_world.translation, e2.matrix_world.translation, aids_coll)
            create_or_update_extraction_aid_line(context, "VISUAL_Extraction_Line_3P_H1_B", 
                                                   e3.matrix_world.translation, e4.matrix_world.translation, aids_coll)
            print("DEBUG refresh_aids: Drew/Updated 3P_H1 aid lines")
        else:
            print("DEBUG refresh_aids: Not exactly 4 '3P_H1_Aid' empties selected for 3P_H1 aid lines.")

        # --- Aid Lines for Horizontal VP2 (H_VP2) ---
        helpers_3p_hvp2 = sorted([e for e in selected_empties if "3P_H2_Aid" in e.name], key=lambda o: o.name)
        if len(helpers_3p_hvp2) == 4:
            print(f"DEBUG refresh_aids: Drawing 3P_H2 aid lines for: {[e.name for e in helpers_3p_hvp2]}")
            e1, e2, e3, e4 = helpers_3p_hvp2[0], helpers_3p_hvp2[1], helpers_3p_hvp2[2], helpers_3p_hvp2[3]
            create_or_update_extraction_aid_line(context, "VISUAL_Extraction_Line_3P_H2_A", 
                                                   e1.matrix_world.translation, e2.matrix_world.translation, aids_coll)
            create_or_update_extraction_aid_line(context, "VISUAL_Extraction_Line_3P_H2_B", 
                                                   e3.matrix_world.translation, e4.matrix_world.translation, aids_coll)
            print("DEBUG refresh_aids: Drew/Updated 3P_H2 aid lines")
        else:
            print("DEBUG refresh_aids: Not exactly 4 '3P_H2_Aid' empties selected for 3P_H2 aid lines.")

        # --- Aid Lines for Vertical VP (V_VP) ---
        helpers_3p_vvp = sorted([e for e in selected_empties if "3P_V_Aid" in e.name], key=lambda o: o.name)
        if len(helpers_3p_vvp) == 4:
            print(f"DEBUG refresh_aids: Drawing 3P_V aid lines for: {[e.name for e in helpers_3p_vvp]}")
            e1, e2, e3, e4 = helpers_3p_vvp[0], helpers_3p_vvp[1], helpers_3p_vvp[2], helpers_3p_vvp[3]
            create_or_update_extraction_aid_line(context, "VISUAL_Extraction_Line_3P_V_A", 
                                                   e1.matrix_world.translation, e2.matrix_world.translation, aids_coll)
            create_or_update_extraction_aid_line(context, "VISUAL_Extraction_Line_3P_V_B", 
                                                   e3.matrix_world.translation, e4.matrix_world.translation, aids_coll)
            print("DEBUG refresh_aids: Drew/Updated 3P_V aid lines")
        else:
            print("DEBUG refresh_aids: Not exactly 4 '3P_V_Aid' empties selected for 3P_V aid lines.")

    else:
        print(f"DEBUG refresh_aids: Mode {ts.current_perspective_type} not implemented for extraction aids.")

    if context.area:
        context.area.tag_redraw()
    print("--- refresh_extraction_aid_lines FINISHED ---")


def get_extraction_aids_collection(context):
    """Gets or creates the collection for visual aid lines for VP extraction."""
    if EXTRACTION_AIDS_COLLECTION not in bpy.data.collections:
        coll = bpy.data.collections.new(EXTRACTION_AIDS_COLLECTION)
        # Link it to the scene's master collection.
        # You might want to make it a child of PERSPECTIVE_HELPER_COLLECTION for better organization if that exists.
        # For now, link to the scene's root collection.
        try:
            context.scene.collection.children.link(coll)
        except RuntimeError: # Already linked (e.g. by another scene)
            pass
        # Optionally, set it to be unselectable in the outliner or hidden from view layer by default if desired.
        # coll.hide_select = True # Makes the collection itself unselectable. Objects inside can still be.
    return bpy.data.collections[EXTRACTION_AIDS_COLLECTION]

def clear_extraction_aids_lines(context, specific_prefix=None):
    """Clears lines from the extraction aids collection.
    If specific_prefix is given (e.g., "VISUAL_Extraction_Line_1P_"), only those are cleared.
    Otherwise, all objects matching a general pattern are cleared.
    """
    aids_coll = get_extraction_aids_collection(context) # Ensures collection exists
    removed_count = 0
    # Iterate over a copy for safe removal
    for obj in list(aids_coll.objects):
        do_remove = False
        if specific_prefix:
            if obj.name.startswith(specific_prefix):
                do_remove = True
        elif obj.name.startswith("VISUAL_Extraction_Line_"): # General catch-all
            do_remove = True

        if do_remove:
            try:
                # Remove material if it's the only user (optional, good cleanup)
                if obj.active_material and obj.active_material.users <= 1 and obj.active_material.name == "MAT_Extraction_Aid_Line":
                    bpy.data.materials.remove(obj.active_material)

                # Remove curve data if it's the only user
                if obj.data and obj.data.name in bpy.data.curves and obj.data.users <= 1:
                    bpy.data.curves.remove(obj.data)
                bpy.data.objects.remove(obj, do_unlink=True) # Unlink and remove
                removed_count += 1
            except ReferenceError: # Object might have been removed by other means
                pass
            except Exception as e:
                print(f"Error removing extraction aid line {obj.name}: {e}")
    # if removed_count > 0:
    #     print(f"Cleared {removed_count} extraction aid lines (prefix: {specific_prefix}).")
    return removed_count

def create_or_update_extraction_aid_line(context, name, p1_world, p2_world, collection):
    """
    Creates a new curve object for an aid line or updates an existing one.
    Points are in world space.
    """
    existing_obj = bpy.data.objects.get(name)

    if existing_obj and existing_obj.type == 'CURVE':
        # Update existing line
        curve_data = existing_obj.data
        if not curve_data.splines: # Should not happen if created correctly
            curve_data.splines.new(type='POLY')
        spline = curve_data.splines[0]
        if len(spline.points) != 2: # Re-initialize points if count is wrong
            while len(spline.points) > 0:
                spline.points.remove(spline.points[0])
            spline.points.add(1) # Creates 2 points

        # Since the object is at world origin, its points are in world space.
        spline.points[0].co = list(p1_world) + [1.0]
        spline.points[1].co = list(p2_world) + [1.0]
        curve_data.update_tag() # Mark for depsgraph update
        return existing_obj
    else:
        # Remove if it exists but is not a curve (shouldn't happen with good naming)
        if existing_obj:
            bpy.data.objects.remove(existing_obj, do_unlink=True)

        # Create new line
        curve_data = bpy.data.curves.new(name=f"{name}_Data", type='CURVE')
        curve_data.dimensions = '3D'
        curve_data.bevel_depth = 0.007 # Thin line for visual aid
        curve_data.bevel_resolution = 0 # Simple bevel

        spline = curve_data.splines.new(type='POLY')
        spline.points.add(1) # 2 points total
        spline.points[0].co = list(p1_world) + [1.0]
        spline.points[1].co = list(p2_world) + [1.0]

        curve_obj = bpy.data.objects.new(name, curve_data)
        curve_obj.location = (0,0,0) # Lines are defined in world space points

        # Assign a simple material for aid lines
        mat_name = "MAT_Extraction_Aid_Line"
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
            if mat.node_tree: # Should always have a node tree after use_nodes=True
                mat.node_tree.nodes.clear()
                output_node = mat.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
                emission_node = mat.node_tree.nodes.new(type='ShaderNodeEmission')
                emission_node.inputs['Color'].default_value = (0.3, 0.7, 1.0, 0.9) # Light blue, fairly opaque
                emission_node.inputs['Strength'].default_value = 1.5 # Make it visible
                mat.node_tree.links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
            mat.blend_method = 'BLEND'
            mat.diffuse_color = (0.3, 0.7, 1.0, 0.9) # Viewport color for solid mode

        if curve_obj.data.materials:
            curve_obj.data.materials[0] = mat
        else:
            curve_obj.data.materials.append(mat)

        curve_obj.hide_select = True # Make the aid lines unselectable

        if name not in collection.objects:
            collection.objects.link(curve_obj)
        return curve_obj

def line_line_intersection_3d(p1, p2, p3, p4, tolerance=1e-3):
    """
    Finds the point of closest approach between two 3D lines L1 (p1-p2) and L2 (p3-p4).
    If the distance between the closest points is within tolerance, their midpoint is returned.
    Otherwise, returns None.
    p1, p2: Vectors defining the first line segment.
    p3, p4: Vectors defining the second line segment.
    tolerance: Maximum distance for lines to be considered intersecting.
    Returns: Intersection point (Vector) or None, and the two closest points C1, C2.
    """
    d1 = p2 - p1
    d2 = p4 - p3

    # Ensure direction vectors are not zero length
    if d1.length_squared < 1e-9 or d2.length_squared < 1e-9:
        # print("DEBUG Intersection: Line segment has zero length.")
        return None, None, None

    # System of equations to find parameters t (for L1) and u (for L2)
    # where the lines are closest.
    # (p1 - p3 + t*d1 - u*d2) . d1 = 0
    # (p1 - p3 + t*d1 - u*d2) . d2 = 0
    #
    # t*(d1.d1) - u*(d2.d1) = (p3-p1).d1
    # t*(d1.d2) - u*(d2.d2) = (p3-p1).d2

    a = d1.dot(d1)
    b = -d2.dot(d1) # same as -d1.dot(d2)
    c = d1.dot(d2)
    d = -d2.dot(d2)

    dp = p3 - p1
    r1 = dp.dot(d1)
    r2 = dp.dot(d2)

    determinant = a * d - b * c

    if abs(determinant) < 1e-9: # Lines are parallel
        # print(f"DEBUG Intersection: Determinant near zero ({determinant}), lines parallel/collinear.")
        # Further checks for collinearity and overlap could be done here.
        # For VP finding, parallel lines don't give a unique VP.
        return None, None, None

    t = (r1 * d - b * r2) / determinant
    u = (a * r2 - r1 * c) / determinant # Note: u is for the line p3 + u*d2

    closest_point_on_l1 = p1 + t * d1
    closest_point_on_l2 = p3 + u * d2 # Corrected from p1 to p3

    distance_squared = (closest_point_on_l1 - closest_point_on_l2).length_squared

    # print(f"DEBUG Intersection: t={t:.4f}, u={u:.4f}, C1={closest_point_on_l1}, C2={closest_point_on_l2}, dist_sq={distance_squared:.6f}")


    if distance_squared < tolerance**2:
        intersection_point = (closest_point_on_l1 + closest_point_on_l2) / 2.0
        return intersection_point, closest_point_on_l1, closest_point_on_l2
    else:
        # print(f"DEBUG Intersection: Lines are skew. Min dist sq: {distance_squared:.4f}")
        return None, closest_point_on_l1, closest_point_on_l2


def get_helpers_collection(context):
    if PERSPECTIVE_HELPER_COLLECTION not in bpy.data.collections:
        coll = bpy.data.collections.new(PERSPECTIVE_HELPER_COLLECTION)
        context.scene.collection.children.link(coll)
    return bpy.data.collections[PERSPECTIVE_HELPER_COLLECTION]

def get_guides_collection(context):
    if PERSPECTIVE_GUIDES_COLLECTION not in bpy.data.collections:
        coll = bpy.data.collections.new(PERSPECTIVE_GUIDES_COLLECTION)
        context.scene.collection.children.link(coll)
    return bpy.data.collections[PERSPECTIVE_GUIDES_COLLECTION]

def get_horizon_control_object():
    return bpy.data.objects.get(HORIZON_CTRL_OBJ_NAME)

def get_horizon_curve_object():
    return bpy.data.objects.get(HORIZON_CURVE_OBJ_NAME)

def get_vanishing_points(specific_prefix_key=None):
    vps = []
    if PERSPECTIVE_HELPER_COLLECTION not in bpy.data.collections:
        return []
    helpers_coll = bpy.data.collections[PERSPECTIVE_HELPER_COLLECTION]
    target_prefix = None
    if specific_prefix_key and specific_prefix_key in VP_TYPE_SPECIFIC_PREFIX_MAP:
        target_prefix = VP_TYPE_SPECIFIC_PREFIX_MAP[specific_prefix_key]

    for obj in helpers_coll.objects:
        if obj.type == 'EMPTY' and obj.name.startswith(VP_PREFIX): # General VP_ check
            if target_prefix: # If a specific type is requested
                if obj.name.startswith(target_prefix): # Check if obj name starts with specific type's prefix
                    vps.append(obj)
            else: # If no specific type, get all VPs
                vps.append(obj)

    # Sort VPs by name for consistent order, crucial for 2P/3P auto-assignment if names aren't exact _1, _2
    vps.sort(key=lambda vp_obj: vp_obj.name)
    return vps


def update_material_color_and_opacity(material, new_color_rgb, new_opacity):
    if material and material.node_tree:
        mix_shader_node = next((n for n in material.node_tree.nodes if n.type == 'ShaderNodeMixShader'), None)
        emission_node = next((n for n in material.node_tree.nodes if n.type == 'ShaderNodeEmission'), None)
        if emission_node:
            emission_node.inputs['Color'].default_value = list(new_color_rgb) + [1.0] # RGBA for emission color
        if mix_shader_node:
            mix_shader_node.inputs[0].default_value = new_opacity # Factor for mix shader
        material.diffuse_color = tuple(list(new_color_rgb) + [new_opacity]) # For viewport display (solid mode)
        return True
    return False

def create_curve_object(context, name, points_data_list, collection,
                        bevel_depth=0.01, opacity=1.0, color_rgb=None, # MODIFIED: Added optional color_rgb=None
                        is_cyclic=False, curve_type='POLY'):
    # Remove existing object and its curve data if it's the only user
    if name in bpy.data.objects:
        old_obj = bpy.data.objects[name]
        if old_obj.data and old_obj.data.name in bpy.data.curves and old_obj.data.users <= 1:
            bpy.data.curves.remove(old_obj.data)
        try:
            bpy.data.objects.remove(old_obj, do_unlink=True)
        except ReferenceError:
            pass 

    curve_data = bpy.data.curves.new(name=f"{name}_Data", type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = bevel_depth
    curve_data.bevel_resolution = 1 
    splines_created_count = 0

    for spline_pts in points_data_list:
        if not spline_pts: continue
        if curve_type == 'POLY' and len(spline_pts) < 2: continue
        if curve_type == 'BEZIER' and not spline_pts: continue

        spline = curve_data.splines.new(type=curve_type)
        if curve_type == 'POLY':
            spline.points.add(len(spline_pts) - 1)
            for idx, pt_co in enumerate(spline_pts):
                spline.points[idx].co = list(pt_co) + [1.0] 
        elif curve_type == 'BEZIER':
            spline.bezier_points.add(len(spline_pts) -1 if spline_pts else 0)
            for idx, pt_co in enumerate(spline_pts):
                bp = spline.bezier_points[idx]
                bp.co = pt_co
                bp.handle_left_type = 'AUTO'
                bp.handle_right_type = 'AUTO'
        
        if spline_pts : 
            spline.use_cyclic_u = is_cyclic and (len(spline_pts) > 1)
        splines_created_count += 1

    if splines_created_count == 0: 
        if curve_data.name in bpy.data.curves:
            bpy.data.curves.remove(curve_data)
        return None

    curve_obj = bpy.data.objects.new(name, curve_data)
    
    # MODIFIED: Determine color to use
    final_color_rgb = color_rgb if color_rgb is not None else \
                      (random.uniform(0.1, 1.0), random.uniform(0.1, 1.0), random.uniform(0.1, 1.0))

    mat_name = f"MAT_{name.replace(':', '_').replace(' ', '_')}" 
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        if mat.node_tree:
            mat.node_tree.nodes.clear()
            output_node = mat.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
            transparent_node = mat.node_tree.nodes.new(type='ShaderNodeBsdfTransparent')
            emission_node = mat.node_tree.nodes.new(type='ShaderNodeEmission')
            mix_shader_node = mat.node_tree.nodes.new(type='ShaderNodeMixShader')

            emission_node.inputs['Color'].default_value = list(final_color_rgb) + [1.0] # MODIFIED to use final_color_rgb
            emission_node.inputs['Strength'].default_value = 3.0 
            mix_shader_node.inputs[0].default_value = opacity 

            mat.node_tree.links.new(transparent_node.outputs['BSDF'], mix_shader_node.inputs[1])
            mat.node_tree.links.new(emission_node.outputs['Emission'], mix_shader_node.inputs[2])
            mat.node_tree.links.new(mix_shader_node.outputs['Shader'], output_node.inputs['Surface'])

        mat.blend_method = 'BLEND' 
        if hasattr(mat, "shadow_method"): mat.shadow_method = 'NONE'
        mat.diffuse_color = tuple(list(final_color_rgb) + [opacity]) # MODIFIED to use final_color_rgb
    else: 
        update_material_color_and_opacity(mat, final_color_rgb, opacity) # MODIFIED to use final_color_rgb

    if curve_obj.data.materials: 
        curve_obj.data.materials[0] = mat
    else:
        curve_obj.data.materials.append(mat)

    target_collection = collection if collection else get_guides_collection(context)
    target_collection.objects.link(curve_obj)
    return curve_obj

def clear_guides_with_prefix(context, prefix_list):
    guides_coll = get_guides_collection(context) # Ensures collection exists
    removed_count = 0
    for obj in list(guides_coll.objects): # Iterate over a copy for safe removal
        for prefix in prefix_list:
            if obj.name.startswith(prefix):
                try:
                    if obj.data and obj.data.name in bpy.data.curves and obj.data.users <= 1:
                        bpy.data.curves.remove(obj.data)
                except ReferenceError: pass
                except Exception as e: print(f"Error removing curve data for {obj.name}: {e}")
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                    removed_count += 1
                except ReferenceError: pass
                except Exception as e: print(f"Error removing object {obj.name}: {e}")
                break 
    return removed_count

def generate_radial_lines_in_plane(vp_loc, density, line_extension, plane='XZ'):
    lines = []
    if density <= 0: return lines
    for i in range(density):
        angle = 2 * math.pi * i / density
        if plane == 'XY': dir_vec = Vector((math.cos(angle), math.sin(angle), 0))
        elif plane == 'XZ': dir_vec = Vector((math.cos(angle), 0, math.sin(angle)))
        elif plane == 'YZ': dir_vec = Vector((0, math.cos(angle), math.sin(angle)))
        else: dir_vec = Vector((math.cos(angle), math.sin(angle), 0)) # Fallback
        dir_vec.normalize()
        lines.append([vp_loc.copy(), vp_loc + dir_vec * line_extension])
    return lines

# -----------------------------------------------------------
# Dynamic Horizon Line Update
# -----------------------------------------------------------
def update_dynamic_horizon_line_curve(context):
    if not hasattr(context.scene, "perspective_tool_settings_splines"):
        return
    tool_settings = context.scene.perspective_tool_settings_splines
    horizon_curve_obj = get_horizon_curve_object()
    if not horizon_curve_obj:
        return

    current_type = tool_settings.current_perspective_type
    points_world = []
    # Hide by default – we'll unhide it when we set valid points.
    horizon_curve_obj.hide_set(True)

    if current_type == 'ONE_POINT':
        vp1p = get_vanishing_points('ONE_POINT')
        if vp1p:
            z_level = vp1p[0].location.z
            center_x = vp1p[0].location.x
            center_y = vp1p[0].location.y
        else:
            # Fallback to horizon control if needed
            horizon_ctrl = get_horizon_control_object()
            if not horizon_ctrl:
                return
            z_level = horizon_ctrl.location.z
            center_x, center_y = 0, 0
        hz_len = tool_settings.horizon_line_length / 2.0
        points_world = [
            Vector((center_x - hz_len, center_y, z_level)),
            Vector((center_x + hz_len, center_y, z_level))
        ]
        horizon_curve_obj.location = (0, 0, 0)
        horizon_curve_obj.rotation_euler = (0, 0, 0)
        # Explicitly unhide the horizon line for ONE_POINT mode.
        horizon_curve_obj.hide_set(False)

    elif current_type == 'TWO_POINT':
        vps_2p = get_vanishing_points('TWO_POINT')
        if len(vps_2p) >= 2:
            points_world = [
                vps_2p[0].location.copy(),
                vps_2p[1].location.copy()
            ]
            horizon_curve_obj.location = Vector((0, 0, 0))
            horizon_curve_obj.hide_set(False)

    elif current_type == 'THREE_POINT': # Corrected from THREE_POINT to THREE_POINT_H as per get_vanishing_points usage
        vps_3p_h = get_vanishing_points('THREE_POINT_H')
        if len(vps_3p_h) >= 2:
            points_world = [
                vps_3p_h[0].location.copy(),
                vps_3p_h[1].location.copy()
            ]
            horizon_curve_obj.location = Vector((0, 0, 0))
            horizon_curve_obj.hide_set(False)

    # Update the spline for the horizon line, if the data exists.
    if horizon_curve_obj.data and horizon_curve_obj.data.splines:
        if not horizon_curve_obj.data.splines: # Ensure spline exists
             horizon_curve_obj.data.splines.new('POLY')

        spline = horizon_curve_obj.data.splines[0]
        if len(points_world) == 2:
            if len(spline.points) != 2:
                #spline.points.clear() # Not a valid method for SplinePoints
                while len(spline.points) > 0:
                    spline.points.remove(spline.points[0])
                spline.points.add(1)   # Adding one point creates a total of 2 points.
            spline.points[0].co = list(points_world[0]) + [1.0]
            spline.points[1].co = list(points_world[1]) + [1.0]
        else: # Default to origin if no valid points
            if len(spline.points) != 2:
                while len(spline.points) > 0:
                    spline.points.remove(spline.points[0])
                spline.points.add(1)
            spline.points[0].co = (0, 0, 0, 1)
            spline.points[1].co = (0, 0, 0, 1)

    horizon_curve_obj.data.bevel_depth = tool_settings.horizon_line_thickness

    h_color_rgb = list(tool_settings.horizon_line_color[:3])
    h_opacity = tool_settings.horizon_line_color[3]
    mat_to_update = None
    if horizon_curve_obj.active_material:
        mat_to_update = horizon_curve_obj.active_material
    elif horizon_curve_obj.data.materials:
        mat_to_update = horizon_curve_obj.data.materials[0]
    if mat_to_update:
        update_material_color_and_opacity(mat_to_update, h_color_rgb, h_opacity)


# -----------------------------------------------------------
# Property Update Callbacks
# -----------------------------------------------------------

# Place with other Property Update Callbacks (e.g., after update_horizon_control_from_prop)

def update_main_vps_visibility(context): # Note: self is not passed if called via lambda from property
    print("DEBUG: update_main_vps_visibility CALLED")
    if not hasattr(context.scene, "perspective_tool_settings_splines"):
        return
    ts = context.scene.perspective_tool_settings_splines
    
    # Get all *main* VPs (those not ending in _Aid or specific helper patterns)
    # This logic might need refinement based on how strictly you name aid empties vs main VPs
    # A simpler way is to get all VPs and then ensure the *aid* empties are handled by their own toggle
    all_vps = get_vanishing_points() # This gets all empties starting with VP_PREFIX

    active_main_vps_to_show = []
    # Determine which main VPs *should* be visible based on current mode
    if ts.current_perspective_type == 'ONE_POINT':
        vp_name = VP_TYPE_SPECIFIC_PREFIX_MAP['ONE_POINT'] + "_1"
        if bpy.data.objects.get(vp_name): active_main_vps_to_show.append(vp_name)
    elif ts.current_perspective_type == 'TWO_POINT':
        for i in ["_1", "_2"]:
            vp_name = VP_TYPE_SPECIFIC_PREFIX_MAP['TWO_POINT'] + i
            if bpy.data.objects.get(vp_name): active_main_vps_to_show.append(vp_name)
    elif ts.current_perspective_type == 'THREE_POINT':
        for i in ["_1", "_2"]: # Horizontal VPs
            vp_name = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_H'] + i
            if bpy.data.objects.get(vp_name): active_main_vps_to_show.append(vp_name)
        vp_name_v = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_V'] + "_1" # Vertical VP
        if bpy.data.objects.get(vp_name_v): active_main_vps_to_show.append(vp_name_v)
    elif ts.current_perspective_type == 'FISH_EYE':
        vp_name = VP_TYPE_SPECIFIC_PREFIX_MAP['FISH_EYE'] + "_1" # Assuming _1 for the center
        if bpy.data.objects.get(vp_name): active_main_vps_to_show.append(vp_name)

    print(f"DEBUG update_main_vps_visibility: Main VPs for mode '{ts.current_perspective_type}': {active_main_vps_to_show}")
    print(f"DEBUG update_main_vps_visibility: ts.show_main_vps is {ts.show_main_vps}")

    for vp_obj in all_vps:
        # Check if this VP is one that *should* be active for the current mode
        if vp_obj.name in active_main_vps_to_show:
            vp_obj.hide_viewport = not ts.show_main_vps # Toggle based on the property
        else:
            # If this VP is NOT for the current mode, it should generally be hidden
            # (clearing logic in switch_perspective_type_prop should remove it, but this is a safety)
            vp_obj.hide_viewport = True 
    
    if context.area:
        context.area.tag_redraw()

def update_vp_empty_colors(self, context): # self is PerspectiveToolSettingsSplines
    tool_settings = self
    vps_1p = get_vanishing_points('ONE_POINT')
    if vps_1p: vps_1p[0].color = list(tool_settings.one_point_vp_empty_color)

    vps_2p = get_vanishing_points('TWO_POINT') # Already sorted by name
    vp1_2p_target = VP_TYPE_SPECIFIC_PREFIX_MAP['TWO_POINT'] + "_1"
    vp2_2p_target = VP_TYPE_SPECIFIC_PREFIX_MAP['TWO_POINT'] + "_2"
    if len(vps_2p) > 0 and vps_2p[0].name.startswith(vp1_2p_target): vps_2p[0].color = list(tool_settings.two_point_vp1_empty_color)
    elif len(vps_2p) > 0: vps_2p[0].color = list(tool_settings.two_point_vp1_empty_color) # Fallback for first
    if len(vps_2p) > 1 and vps_2p[1].name.startswith(vp2_2p_target): vps_2p[1].color = list(tool_settings.two_point_vp2_empty_color)
    elif len(vps_2p) > 1: vps_2p[1].color = list(tool_settings.two_point_vp2_empty_color) # Fallback for second


    vps_3ph = get_vanishing_points('THREE_POINT_H') # Sorted
    vp1_3ph_target = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_H'] + "_1"
    vp2_3ph_target = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_H'] + "_2"
    if len(vps_3ph) > 0 and vps_3ph[0].name.startswith(vp1_3ph_target): vps_3ph[0].color = list(tool_settings.three_point_vp_h1_empty_color)
    elif len(vps_3ph) > 0: vps_3ph[0].color = list(tool_settings.three_point_vp_h1_empty_color)
    if len(vps_3ph) > 1 and vps_3ph[1].name.startswith(vp2_3ph_target): vps_3ph[1].color = list(tool_settings.three_point_vp_h2_empty_color)
    elif len(vps_3ph) > 1: vps_3ph[1].color = list(tool_settings.three_point_vp_h2_empty_color)

    vps_3pv = get_vanishing_points('THREE_POINT_V') # Sorted
    vp1_3pv_target = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_V'] + "_1"
    if vps_3pv and vps_3pv[0].name.startswith(vp1_3pv_target) : vps_3pv[0].color = list(tool_settings.three_point_vp_v_empty_color)
    elif vps_3pv : vps_3pv[0].color = list(tool_settings.three_point_vp_v_empty_color)

    vps_fe = get_vanishing_points('FISH_EYE')
    if vps_fe: # Should typically only be one for FE center
        # Apply color to all found FE VPs, though usually there's just one primary.
        for vp_fe in vps_fe:
            vp_fe.color = list(tool_settings.fish_eye_vp_empty_color)


    if context.area: context.area.tag_redraw()

def update_guides_visuals_from_props(self, context): # self is PerspectiveToolSettingsSplines
    tool_settings = self # self is PerspectiveToolSettingsSplines
    guides_coll = get_guides_collection(context)
    
    # Opacity and thickness are still global
    default_opacity = tool_settings.guide_curves_opacity
    # Thickness is handled by create_curve_object's bevel_depth and operator generate functions reading guide_curves_thickness

    for obj in guides_coll.objects:
        if obj.type == 'CURVE' and obj.name != HORIZON_CURVE_OBJ_NAME:
            if obj.data: # Update bevel depth (thickness)
                obj.data.bevel_depth = tool_settings.guide_curves_thickness

            mat = obj.active_material if obj.active_material else (obj.data.materials[0] if obj.data.materials else None)
            if mat:
                # Color is set randomly at creation, so we only update opacity here
                # Retrieve the existing emission color to preserve it
                emission_node = next((n for n in mat.node_tree.nodes if n.type == 'ShaderNodeEmission'), None)
                if emission_node:
                    existing_rgb_color = list(emission_node.inputs['Color'].default_value[:3])
                    update_material_color_and_opacity(mat, existing_rgb_color, default_opacity)
    if context.area: context.area.tag_redraw()

def update_horizon_visuals_from_props(self, context):
    update_dynamic_horizon_line_curve(context)

def update_horizon_control_from_prop(self, context): # self is horizon_y_level property
    horizon_ctrl = get_horizon_control_object()
    if horizon_ctrl:
        if abs(horizon_ctrl.location.z - self.horizon_y_level) > 0.001: # self here is PerspectiveToolSettingsSplines
            horizon_ctrl.location.z = self.horizon_y_level
    update_dynamic_horizon_line_curve(context)

# Place this in your "Property Update Callbacks" section

# Place this in your "Property Update Callbacks" section

# Place this in your "Property Update Callbacks" section

def switch_perspective_type_prop(self, context): # self is PerspectiveToolSettingsSplines
    global previous_perspective_type_on_switch
    tool_settings = self 
    current_new_type = tool_settings.current_perspective_type

    print(f"DEBUG switch_prop: Previous Type = '{previous_perspective_type_on_switch}', New Type = '{current_new_type}'")

    # 1. Clearing previous type's VPs & Guides
    if previous_perspective_type_on_switch != 'NONE' and previous_perspective_type_on_switch != current_new_type:
        print(f"  Clearing VPs & Guides for previous type: {previous_perspective_type_on_switch}")
        try:
            bpy.ops.perspective_splines.clear_type_guides('EXEC_DEFAULT', type_filter_prop=previous_perspective_type_on_switch)
        except Exception as e:
            print(f"  ERROR during clear_type_guides for '{previous_perspective_type_on_switch}': {e}")

    # 2. Creating default VP elements for the NEW type.
    try:
        if current_new_type == 'ONE_POINT':
            print(f"  Setting up default VP for ONE_POINT mode...")
            PERSPECTIVE_OT_generate_one_point_splines.create_default_one_point(context)
        elif current_new_type == 'TWO_POINT':
            print(f"  Setting up default VPs for TWO_POINT mode...")
            PERSPECTIVE_OT_create_2p_vps_if_needed.create_default_two_point_vps(context)
        elif current_new_type == 'THREE_POINT':
            print(f"  Setting up default VPs for THREE_POINT mode...")
            PERSPECTIVE_OT_create_3p_vps_if_needed.create_default_three_point_vps(context)
        elif current_new_type == 'FISH_EYE':
            print(f"  Setting up default VP for FISH_EYE mode...")
            PERSPECTIVE_OT_generate_fish_eye_splines.create_default_fish_eye_center(context)
        elif current_new_type == 'NONE':
            print(f"  Switched to NONE mode. VPs for '{previous_perspective_type_on_switch}' should be cleared.")
            
    except Exception as e:
        print(f"  ERROR during default VP setup for {current_new_type}: {e}")
    
    # 3. Updating common visuals (VP colors, horizon line, aid lines)
    try:
        print(f"  Updating VP empty colors for mode: {current_new_type}")
        update_vp_empty_colors(tool_settings, context)
    except Exception as e:
        print(f"  ERROR updating VP colors: {e}")
    
    try:
        print(f"  Updating dynamic horizon line for mode: {current_new_type}")
        update_dynamic_horizon_line_curve(context) 
    except Exception as e:
        print(f"  ERROR updating horizon line: {e}")

    print(f"  Refreshing extraction aid lines for mode: {current_new_type}")
    refresh_extraction_aid_lines(context)

    previous_perspective_type_on_switch = current_new_type
    if context.area:
        context.area.tag_redraw()
    print(f"--- Switch to {current_new_type} finished. ---")


# -----------------------------------------------------------
# Custom Properties
# -----------------------------------------------------------

# -----------------------------------------------------------
# Custom Properties
# -----------------------------------------------------------

# -----------------------------------------------------------
# Custom Properties
# -----------------------------------------------------------

class PerspectiveToolSettingsSplines(PropertyGroup):
    horizon_y_level: FloatProperty(
        name="1P Horizon Z",
        default=0.0,
        update=update_horizon_control_from_prop, # Assumes this callback exists
        description="Z-level for the 1P horizon line control object"
    )
    horizon_line_length: FloatProperty(
        name="1P Horizon Length",
        default=200.0,
        min=1.0,
        update=update_horizon_visuals_from_props # Assumes this callback exists
    )
    horizon_line_thickness: FloatProperty(
        name="Horizon Thickness",
        default=0.02,
        min=0.001,
        max=0.5,
        update=update_horizon_visuals_from_props
    )
    horizon_line_color: FloatVectorProperty(
        name="Horizon Color",
        subtype='COLOR_GAMMA',
        size=4,
        default=(0.9, 0.9, 0.2, 1.0),
        min=0.0,
        max=1.0,
        update=update_horizon_visuals_from_props
    )

    guide_curves_thickness: FloatProperty(
        name="Guide Lines Thickness",
        default=0.01,
        min=0.001,
        max=0.5,
        update=update_guides_visuals_from_props # Assumes this callback exists
    )
    guide_curves_opacity: FloatProperty(
        name="Guide Lines Opacity",
        default=0.8,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
        update=update_guides_visuals_from_props
    )

    # VP Empty colors
    one_point_vp_empty_color: FloatVectorProperty(
        name="1P VP Empty Color", subtype='COLOR', size=4, default=(1.0, 0.7, 0.2, 1.0),
        min=0.0, max=1.0, update=update_vp_empty_colors # Assumes this callback exists
    )
    two_point_vp1_empty_color: FloatVectorProperty(
        name="2P VP1 Empty Color", subtype='COLOR', size=4, default=(1.0, 0.4, 0.4, 1.0),
        min=0.0, max=1.0, update=update_vp_empty_colors
    )
    two_point_vp2_empty_color: FloatVectorProperty(
        name="2P VP2 Empty Color", subtype='COLOR', size=4, default=(0.4, 1.0, 0.4, 1.0),
        min=0.0, max=1.0, update=update_vp_empty_colors
    )
    three_point_vp_h1_empty_color: FloatVectorProperty(
        name="3P VP H1 Empty Color", subtype='COLOR', size=4, default=(1.0, 0.2, 0.2, 1.0),
        min=0.0, max=1.0, update=update_vp_empty_colors
    )
    three_point_vp_h2_empty_color: FloatVectorProperty(
        name="3P VP H2 Empty Color", subtype='COLOR', size=4, default=(0.2, 1.0, 0.2, 1.0),
        min=0.0, max=1.0, update=update_vp_empty_colors
    )
    three_point_vp_v_empty_color: FloatVectorProperty(
        name="3P VP V Empty Color", subtype='COLOR', size=4, default=(0.2, 0.2, 1.0, 1.0),
        min=0.0, max=1.0, update=update_vp_empty_colors
    )
    fish_eye_vp_empty_color: FloatVectorProperty(
        name="FE VP Empty Color", subtype='COLOR', size=4, default=(0.5, 0.2, 0.8, 1.0),
        min=0.0, max=1.0, update=update_vp_empty_colors
    )

    # --- One Point ---
    one_point_grid_density_radial: IntProperty(name="Radial Lines Density", default=16, min=2)
    one_point_grid_density_ortho_x: IntProperty(name="Horiz. Parallels Density", default=7, min=0)
    one_point_grid_density_ortho_y: IntProperty(name="Vert. Parallels Density", default=7, min=0)
    one_point_draw_radial: BoolProperty(name="Draw Radial Lines", default=True)
    one_point_draw_ortho_x: BoolProperty(name="Draw Horiz. Parallels", default=True)
    one_point_draw_ortho_y: BoolProperty(name="Draw Vert. Parallels", default=True)
    one_point_grid_extent: FloatProperty(name="Ortho Grid Extent Factor", default=1.0, min=0.1)
    one_point_line_extension: FloatProperty(name="Radial Line Length", default=DEFAULT_LINE_EXTENSION, min=1.0)

    # --- Two Point ---
    two_point_grid_density_vp1: IntProperty(name="VP1 Lines Density", default=10, min=1)
    two_point_grid_density_vp2: IntProperty(name="VP2 Lines Density", default=10, min=1)
    two_point_grid_density_vertical: IntProperty(name="Vertical Lines Density", default=9, min=0)
    two_point_verticals_x_spacing_factor: FloatProperty(name="Verticals X Spacing Factor", default=1.0, min=0.1, max=5.0)
    two_point_grid_height: FloatProperty(name="Vertical Line Height", default=20.0, min=0.1)
    two_point_grid_depth_offset: FloatProperty(name="Verticals' Y Plane Offset", default=0.0)
    two_point_line_extension: FloatProperty(name="Radial Line Length", default=200.0, min=1.0)

    # --- Three Point ---
    three_point_line_extension: FloatProperty(name="Radial Line Length", default=200.0, min=1.0)
    three_point_vp_h1_density: IntProperty(name="H1 Lines Density", default=8, min=1)
    three_point_vp_h2_density: IntProperty(name="H2 Lines Density", default=8, min=1)
    three_point_vp_v_density: IntProperty(name="V Lines Density", default=8, min=1)

    # --- Fish Eye ---
    fish_eye_strength: FloatProperty(name="Distortion Strength", default=0.5, min=-1.0, max=1.0)
    fish_eye_grid_radial: IntProperty(name="Longitude Lines", default=16, min=3)
    fish_eye_grid_concentric: IntProperty(name="Latitude Lines", default=8, min=1)
    fish_eye_grid_radius: FloatProperty(name="Sphere Radius", default=15.0, min=0.1)
    fish_eye_segments_per_curve: IntProperty(name="Curve Smoothness", default=24, min=4, max=64)
    fish_eye_draw_latitude: BoolProperty(name="Draw Latitude Lines", default=True)
    fish_eye_horizontal_scale: FloatProperty(name="Fish Eye Horizontal Scale", default=1.0, min=0.1, max=5.0)

    current_perspective_type: EnumProperty(
        name="Perspective Mode",
        items=[('NONE', "None", "No perspective guides active"),
               ('ONE_POINT', "One Point", "One-point perspective"),
               ('TWO_POINT', "Two Point", "Two-point perspective"),
               ('THREE_POINT', "Three Point", "Three-point perspective"),
               ('FISH_EYE', "Fish Eye", "Fisheye (spherical) perspective cage")],
        default='NONE',
        update=switch_perspective_type_prop # Assumes this callback exists
    )
    camera_eye_height: FloatProperty(name="Camera Eye Height", default=1.6, min=0.1)
    camera_distance: FloatProperty(name="Camera Distance from Target", default=15.0, min=1.0)

    # --- Grid Creation Properties ---
    grid_active_plane: EnumProperty(
        name="Active Grid Plane",
        items=[('FRONT', "Front (YZ)", "Create grid on the YZ plane"),
               ('BACK', "Back (YZ)", "Create grid on the YZ plane (offset for back)"),
               ('TOP', "Top (XY)", "Create grid on the XY plane"),
               ('BOTTOM', "Bottom (XY)", "Create grid on the XY plane (offset for bottom)"),
               ('LEFT', "Left (XZ)", "Create grid on the XZ plane (offset for left)"),
               ('RIGHT', "Right (XZ)", "Create grid on the XZ plane")],
        default='FRONT'
    )
    grid_center: FloatVectorProperty(name="Grid Box Center", size=3, default=(0,0,0))
    grid_size: FloatVectorProperty(name="Grid Box Size (X,Y,Z)", size=3, default=(10,10,10), min=0.1)
    grid_subdivisions_u: IntProperty(name="Subdivisions U", default=10, min=1)
    grid_subdivisions_v: IntProperty(name="Subdivisions V", default=10, min=1)
    grid_draw_front: BoolProperty(name="Draw Front Grid", default=True)
    grid_draw_back: BoolProperty(name="Draw Back Grid", default=False)
    grid_draw_top: BoolProperty(name="Draw Top Grid", default=True)
    grid_draw_bottom: BoolProperty(name="Draw Bottom Grid", default=False)
    grid_draw_left: BoolProperty(name="Draw Left Grid", default=False)
    grid_draw_right: BoolProperty(name="Draw Right Grid", default=False)

    # --- Line Trimming Properties ---
    trim_margin: FloatProperty(
        name="Trim Margin (0-1)", default=0.05, min=0.0, max=0.5,
        description="Margin outside camera view for trimming (0=exact edge)"
    )
    trim_view_margin: FloatProperty(
        name="View Margin", default=0.05, min=0.0, max=0.49, subtype='FACTOR',
        description="Margin from camera view edges (0.0 to 0.49). Lines inside this margin are always kept."
    )
    trim_keep_near_border_distance: FloatProperty(
        name="Keep Near Border", default=0.1, min=0.0, max=0.5, subtype='FACTOR',
        description="Normalized distance outside the camera border to keep and trim lines (0.0 = only inside, 0.1 = keep lines just outside border)."
    )
    trim_min_visible_segment_length: FloatProperty(
        name="Min Segment Length", default=0.05, min=0.001, max=200.0,
        description="Minimum world-space length for a trimmed line segment to be kept."
    )
    trim_delete_lines_outside_strict_view: BoolProperty(
        name="Delete Only Far Lines", default=False,
        description="If true, only lines far from the camera view are deleted. Lines near the border are kept."
    )
    trim_deletion_distance_threshold: FloatProperty(
        name="Deletion Distance Threshold", default=0.2, min=0.0, max=2.0,
        description="Normalized distance outside the camera view to delete lines (used only if 'Delete Only Far Lines' is true)."
    )
    trim_start_percent: FloatProperty(
        name="Start % Inside", default=0.0, min=0.0, max=0.9, subtype='FACTOR',
        description="Where to start the trimmed line as a percentage of the visible segment (0 = at border, 0.2 = 20% into view)"
    )
    trim_end_percent: FloatProperty(
        name="End % Inside", default=1.0, min=0.1, max=1.0, subtype='FACTOR',
        description="Where to end the trimmed line as a percentage of the visible segment (1 = at far border, 0.8 = 80% into view)"
    )

    # --- Perspective Extraction Visual Aids ---
    show_extraction_helper_lines: BoolProperty(
        name="Show Aid Lines", # Shortened for UI
        description="Draw temporary lines between selected helper empties used for VP extraction.",
        default=False,
        update=lambda self, context: refresh_extraction_aid_lines(context) # Assumes this callback exists
    )

    # --- Main Vanishing Points Visibility ---
    show_main_vps: BoolProperty(
        name="Show Main VPs",
        description="Toggle visibility of the main perspective vanishing point empties (VP_1P_1, VP_2P_1, etc.)",
        default=True, # VPs should be visible by default
        update=lambda self, context: update_main_vps_visibility(context) # NEW callback needed
    )
# End of PerspectiveToolSettingsSplines class

# -----------------------------------------------------------
# Helper: Add Vanishing Point Empty if Missing
# -----------------------------------------------------------
# -----------------------------------------------------------
# Operators
# -----------------------------------------------------------

# ... (Keep all your existing code before the operators, including bl_info, utility functions, properties, etc.) ...

# MAKE SURE 'get_guides_collection' and HORIZON_CURVE_OBJ_NAME are defined before this point.


# Place this with your other Operator classes

# Place with other Operator classes

# --- Operators for 3-Point Perspective - H_VP1 ---

class PERSPECTIVE_OT_delete_all_helpers(bpy.types.Operator):
    """Deletes ALL helper empties from the aids collection."""
    bl_idname = "perspective_splines.delete_all_helpers"
    bl_label = "Delete All Helper Empties"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # We can run this if the collection exists and has objects
        aids_coll = bpy.data.collections.get(EXTRACTION_AIDS_COLLECTION)
        return aids_coll and len(aids_coll.objects) > 0

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        
        # Create a list of helper empties to delete to avoid issues while iterating
        helpers_to_delete = [
            obj for obj in aids_coll.objects 
            if obj.type == 'EMPTY' and "_Aid" in obj.name
        ]

        if not helpers_to_delete:
            self.report({'INFO'}, "No helper empties found to delete.")
            return {'CANCELLED'}

        deleted_count = len(helpers_to_delete)
        
        # Deselect everything to avoid context issues
        if context.active_object:
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')

        # Remove the objects
        for obj in helpers_to_delete:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except ReferenceError:
                # Object might have already been removed by another process
                pass
            except Exception as e:
                print(f"Could not remove helper empty {obj.name}: {e}")

        # Also clear any visual lines that might be left over
        clear_extraction_aids_lines(context)

        self.report({'INFO'}, f"Deleted {deleted_count} helper empties.")
        
        # Refresh the UI
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}

class PERSPECTIVE_OT_extract_3p_v_from_empties(bpy.types.Operator):
    """Extracts and sets the main vertical VP from 4 selected helper empties."""
    bl_idname = "perspective_splines.extract_3p_v_from_empties"
    bl_label = "Set 3P V_VP from Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if not ts or ts.current_perspective_type != 'THREE_POINT':
            cls.poll_message_set("Switch to 'Three Point' mode.")
            return False
        selected_empties = [obj for obj in context.selected_objects if obj.type == 'EMPTY' and "3P_V_Aid" in obj.name]
        if len(selected_empties) != 4:
            cls.poll_message_set(f"Select 4 '3P_V_Aid' empties. Found: {len(selected_empties)}")
            return False
        return True

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        selected_empties = sorted(
            [obj for obj in context.selected_objects if obj.type == 'EMPTY' and "3P_V_Aid" in obj.name],
            key=lambda o: o.name
        )
        p1_loc = selected_empties[0].matrix_world.translation
        p2_loc = selected_empties[1].matrix_world.translation
        p3_loc = selected_empties[2].matrix_world.translation
        p4_loc = selected_empties[3].matrix_world.translation

        intersection_pt, c1, c2 = line_line_intersection_3d(p1_loc, p2_loc, p3_loc, p4_loc, tolerance=0.05)

        if intersection_pt:
            vp_target_name = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_V'] + "_1"
            # Ensure 3P VPs exist (this creates the vertical VP as well)
            PERSPECTIVE_OT_create_3p_vps_if_needed.create_default_three_point_vps(context)
            main_vp_empty = bpy.data.objects.get(vp_target_name)
            if not main_vp_empty:
                self.report({'ERROR'}, f"Failed to get or create main VP: {vp_target_name}")
                return {'CANCELLED'}

            main_vp_empty.location = intersection_pt
            update_vp_empty_colors(ts, context)

            try:
                bpy.ops.perspective_splines.generate_3p_v_lines('EXEC_DEFAULT')
            except Exception as e:
                self.report({'WARNING'}, f"Error auto-generating V-VP lines: {e}")

            self.report({'INFO'}, f"Set {vp_target_name} to {main_vp_empty.location}. 3P guides for vertical VP updated.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Lines for 3P vertical VP do not intersect closely enough. Adjust your '3P_V_Aid' empties.")
            return {'CANCELLED'}


class PERSPECTIVE_OT_add_3p_v_vp_helpers(bpy.types.Operator):
    """Adds 4 named empties for 3-Point Perspective vertical VP extraction."""
    bl_idname = "perspective_splines.add_3p_v_vp_helpers"
    bl_label = "Add Helpers for 3P V_VP"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        original_active = context.active_object
        original_selection = list(context.selected_objects)
        bpy.ops.object.select_all(action='DESELECT')

        base_name = "3P_V_Aid"  # The unique part for vertical helpers.
        # Example positions – adjust these as necessary. The following sets up two pairs:
        locs = [
            Vector((-1, 0, 2)), Vector((1, 0, 2)),   # Top helper pair
            Vector((-0.5, 0, 0)), Vector((0.5, 0, 0))  # Bottom helper pair
        ]
        suffixes = ["L1_P1", "L1_P2", "L2_P1", "L2_P2"]
        created_empties = []

        for i in range(4):
            unique_name_base = f"{suffixes[i]}_{base_name}"
            final_name = unique_name_base
            name_idx = 1
            while bpy.data.objects.get(final_name):
                final_name = f"{unique_name_base}.{str(name_idx).zfill(3)}"
                name_idx += 1

            bpy.ops.object.empty_add(type='ARROWS', radius=0.2, align='WORLD', location=locs[i])
            new_empty = context.active_object
            if new_empty:
                new_empty.name = final_name
                new_empty.empty_display_size = 0.3
                for coll in list(new_empty.users_collection):
                    coll.objects.unlink(new_empty)
                if new_empty.name not in aids_coll.objects:
                    aids_coll.objects.link(new_empty)
                new_empty.select_set(True)
                created_empties.append(new_empty)
            else:
                self.report({'WARNING'}, f"Failed to create empty {final_name}")

        if created_empties:
            context.view_layer.objects.active = created_empties[-1]
        else:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj and obj.name in bpy.data.objects:
                    try:
                        obj.select_set(True)
                    except ReferenceError:
                        pass
            if original_active and original_active.name in bpy.data.objects:
                try:
                    context.view_layer.objects.active = original_active
                except ReferenceError:
                    pass

        self.report({'INFO'}, "Added 4 helpers for 3P V_VP.")
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if ts and ts.show_extraction_helper_lines:
            refresh_extraction_aid_lines(context)
        return {'FINISHED'}


class PERSPECTIVE_OT_extract_3p_h_vp2_from_empties(bpy.types.Operator):
    """Extracts and sets the main H_VP2 from 4 selected helper empties."""
    bl_idname = "perspective_splines.extract_3p_h_vp2_from_empties"
    bl_label = "Set 3P H_VP2 from Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if not ts or ts.current_perspective_type != 'THREE_POINT':
            cls.poll_message_set("Switch to 'Three Point' mode.")
            return False
        selected_empties = [obj for obj in context.selected_objects if obj.type == 'EMPTY' and "3P_H2_Aid" in obj.name]
        if len(selected_empties) != 4:
            cls.poll_message_set(f"Select 4 '3P_H2_Aid' empties. Found: {len(selected_empties)}")
            return False
        return True

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        selected_empties = sorted(
            [obj for obj in context.selected_objects if obj.type == 'EMPTY' and "3P_H2_Aid" in obj.name],
            key=lambda o: o.name
        )
        p1_loc = selected_empties[0].matrix_world.translation  # First line point
        p2_loc = selected_empties[1].matrix_world.translation
        p3_loc = selected_empties[2].matrix_world.translation  # Second line point
        p4_loc = selected_empties[3].matrix_world.translation

        intersection_pt, c1, c2 = line_line_intersection_3d(p1_loc, p2_loc, p3_loc, p4_loc, tolerance=0.05)

        if intersection_pt:
            vp_target_name = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_H'] + "_2"
            # Ensure all main 3P VPs exist (this will update/create H_VPs and the vertical VP)
            PERSPECTIVE_OT_create_3p_vps_if_needed.create_default_three_point_vps(context)
            main_vp_empty = bpy.data.objects.get(vp_target_name)
            if not main_vp_empty:
                self.report({'ERROR'}, f"Failed to get or create main VP: {vp_target_name}")
                return {'CANCELLED'}

            main_vp_empty.location = intersection_pt
            update_vp_empty_colors(ts, context)

            try:
                bpy.ops.perspective_splines.generate_3p_h2_lines('EXEC_DEFAULT')
            except Exception as e:
                self.report({'WARNING'}, f"Error auto-generating H_VP2 lines: {e}")

            self.report({'INFO'}, f"Set {vp_target_name} to {main_vp_empty.location}. 3P guides for H_VP2 updated.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Lines for 3P-H_VP2 do not intersect closely enough. Adjust your '3P_H2_Aid' empties.")
            return {'CANCELLED'}


class PERSPECTIVE_OT_add_3p_h_vp2_helpers(bpy.types.Operator):
    """Adds 4 named empties for 3-Point Perspective H_VP2 extraction."""
    bl_idname = "perspective_splines.add_3p_h_vp2_helpers"
    bl_label = "Add Helpers for 3P H_VP2"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        original_active = context.active_object
        original_selection = list(context.selected_objects)
        bpy.ops.object.select_all(action='DESELECT')

        base_name = "3P_H2_Aid"  # This distinguishes H_VP2 helpers.
        # Example positions – adjust these as needed for your workflow:
        locs = [
            Vector((4, -1, 1)), Vector((6, -0.5, 1)),  # First line for H_VP2
            Vector((4, 1, 1)),  Vector((6, 0.5, 1))     # Second line for H_VP2
        ]
        suffixes = ["L1_P1", "L1_P2", "L2_P1", "L2_P2"]
        created_empties = []

        for i in range(4):
            unique_name_base = f"{suffixes[i]}_{base_name}"
            final_name = unique_name_base
            name_idx = 1
            while bpy.data.objects.get(final_name):
                final_name = f"{unique_name_base}.{str(name_idx).zfill(3)}"
                name_idx += 1

            bpy.ops.object.empty_add(type='ARROWS', radius=0.2, align='WORLD', location=locs[i])
            new_empty = context.active_object
            if new_empty:
                new_empty.name = final_name
                new_empty.empty_display_size = 0.3
                for coll in list(new_empty.users_collection):
                    coll.objects.unlink(new_empty)
                if new_empty.name not in aids_coll.objects:
                    aids_coll.objects.link(new_empty)
                new_empty.select_set(True)
                created_empties.append(new_empty)
            else:
                self.report({'WARNING'}, f"Failed to create empty {final_name}")
        
        if created_empties:
            context.view_layer.objects.active = created_empties[-1]
        else:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj and obj.name in bpy.data.objects:
                    try:
                        obj.select_set(True)
                    except ReferenceError:
                        pass
            if original_active and original_active.name in bpy.data.objects:
                try:
                    context.view_layer.objects.active = original_active
                except ReferenceError:
                    pass

        self.report({'INFO'}, f"Added 4 helpers for 3P H_VP2.")
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if ts and ts.show_extraction_helper_lines:
            refresh_extraction_aid_lines(context)
        return {'FINISHED'}


from bpy.props import BoolProperty

class PERSPECTIVE_SPLINES_OT_remove_selected_helper_empty(bpy.types.Operator):
    bl_idname = "perspective_splines.remove_selected_helper_empty"
    bl_label = "Remove Selected Helper"
    bl_options = {'REGISTER', 'UNDO'}

    active: BoolProperty(
        name="Active",
        default=False,
        description="Flag to indicate if the VP/Ctrl is active"
    )

    @classmethod
    def poll(cls, context):
        act_obj = context.active_object
        return act_obj and act_obj.type == 'EMPTY' and \
            (act_obj.name.startswith(VP_PREFIX) or act_obj.name == HORIZON_CTRL_OBJ_NAME)

    def execute(self, context):
        # Your removal logic here...
        obj_to_remove = context.active_object
        try:
            bpy.data.objects.remove(obj_to_remove, do_unlink=True)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Removed helper: {obj_to_remove.name}.")
        return {'FINISHED'}


class PERSPECTIVE_OT_add_3p_h_vp1_helpers(bpy.types.Operator):
    """Adds 4 named empties for 3-Point Perspective H_VP1 extraction."""
    bl_idname = "perspective_splines.add_3p_h_vp1_helpers"
    bl_label = "Add Helpers for 3P H_VP1"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        original_active = context.active_object
        original_selection = list(context.selected_objects)
        bpy.ops.object.select_all(action='DESELECT')

        base_name = "3P_H1_Aid" # Specific to H_VP1
        # Example positions (adjust as needed, e.g., left side of view)
        locs = [
            Vector((-6, -1, 1)), Vector((-4, -0.5, 1)), # Line 1 for H_VP1
            Vector((-6, 1, 1)), Vector((-4, 0.5, 1))   # Line 2 for H_VP1
        ]
        suffixes = ["L1_P1", "L1_P2", "L2_P1", "L2_P2"]
        created_empties = []

        for i in range(4):
            unique_name_base = f"{suffixes[i]}_{base_name}"
            final_name = unique_name_base
            name_idx = 1
            while bpy.data.objects.get(final_name): # Ensure unique name
                final_name = f"{unique_name_base}.{str(name_idx).zfill(3)}"
                name_idx += 1
            
            bpy.ops.object.empty_add(type='ARROWS', radius=0.2, align='WORLD', location=locs[i]) # Different display type
            new_empty = context.active_object
            if new_empty:
                new_empty.name = final_name
                new_empty.empty_display_size = 0.3 
                
                for coll in list(new_empty.users_collection):
                    coll.objects.unlink(new_empty)
                if new_empty.name not in aids_coll.objects:
                    aids_coll.objects.link(new_empty)
                
                new_empty.select_set(True)
                created_empties.append(new_empty)
            else:
                self.report({'WARNING'}, f"Failed to create empty {final_name}")
        
        if created_empties:
            context.view_layer.objects.active = created_empties[-1]
        else:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj and obj.name in bpy.data.objects:
                    try: obj.select_set(True)
                    except ReferenceError: pass
            if original_active and original_active.name in bpy.data.objects:
                 try: context.view_layer.objects.active = original_active
                 except ReferenceError: pass

        self.report({'INFO'}, f"Added 4 helpers for 3P-H_VP1.")
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if ts and ts.show_extraction_helper_lines:
            refresh_extraction_aid_lines(context)
        return {'FINISHED'}

class PERSPECTIVE_OT_extract_3p_h_vp1_from_empties(bpy.types.Operator):
    """Extracts and sets the main VP_3P_H_1 from 4 selected helper empties."""
    bl_idname = "perspective_splines.extract_3p_h_vp1_from_empties"
    bl_label = "Set 3P H_VP1 from Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if not ts or ts.current_perspective_type != 'THREE_POINT':
            cls.poll_message_set("Switch to 'Three Point' mode.")
            return False
        selected_empties = [obj for obj in context.selected_objects if obj.type == 'EMPTY' and "3P_H1_Aid" in obj.name]
        if len(selected_empties) != 4:
            cls.poll_message_set(f"Select 4 '3P_H1_Aid' empties. Found: {len(selected_empties)}")
            return False
        return True

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        selected_empties = sorted(
            [obj for obj in context.selected_objects if obj.type == 'EMPTY' and "3P_H1_Aid" in obj.name],
            key=lambda o: o.name
        )
        # Poll ensures len is 4

        p1_loc = selected_empties[0].matrix_world.translation # L1_P1
        p2_loc = selected_empties[1].matrix_world.translation # L1_P2
        p3_loc = selected_empties[2].matrix_world.translation # L2_P1
        p4_loc = selected_empties[3].matrix_world.translation # L2_P2

        intersection_pt, c1, c2 = line_line_intersection_3d(p1_loc, p2_loc, p3_loc, p4_loc, tolerance=0.05)

        if intersection_pt:
            # Target main VP for 3P Horizontal 1
            vp_target_name = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_H'] + "_1" 
            
            # Ensure all main 3P VPs & Horizon are set up or exist
            PERSPECTIVE_OT_create_3p_vps_if_needed.create_default_three_point_vps(context)
            main_vp_empty = bpy.data.objects.get(vp_target_name) # Re-fetch

            if not main_vp_empty:
                 self.report({'ERROR'}, f"Failed to get or create main VP: {vp_target_name}")
                 return {'CANCELLED'}

            main_vp_empty.location = intersection_pt
            # The create_default_three_point_vps method should ensure Z is on horizon for H VPs
            
            update_vp_empty_colors(ts, context)
            
            try:
                # This will use the new location of VP_3P_H_1
                bpy.ops.perspective_splines.generate_3p_h1_lines('EXEC_DEFAULT') 
                # update_dynamic_horizon_line_curve is also called within generate_3p_h1_lines
            except Exception as e:
                self.report({'WARNING'}, f"Error auto-generating H_VP1 lines: {e}")

            self.report({'INFO'}, f"Set {vp_target_name} to {main_vp_empty.location}. 3P guides for H_VP1 updated.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Lines for 3P-H_VP1 do not intersect closely. Adjust '3P_H1_Aid' empties.")
            return {'CANCELLED'}

class PERSPECTIVE_OT_select_helper_empties(bpy.types.Operator):
    """Selects helper empties based on the current perspective mode or a specific tag."""
    bl_idname = "perspective_splines.select_helper_empties"
    bl_label = "Select Helper Empties"
    bl_options = {'REGISTER', 'UNDO'}

    # Define a property to specify which set of helpers to select
    helper_set_identifier: StringProperty(
        name="Helper Set ID",
        description="Identifier for the set of helpers (e.g., '1P_Aid', '2P_VP1_Aid', 'ALL_AIDS')",
        default="ALL_AIDS" 
    )

    @classmethod
    def poll(cls, context):
        # This operator can always run if there's an extraction aids collection
        return EXTRACTION_AIDS_COLLECTION in bpy.data.collections

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        if not aids_coll.objects:
            self.report({'INFO'}, "No helper empties found in the aid collection.")
            return {'CANCELLED'}

        bpy.ops.object.select_all(action='DESELECT') # Deselect everything first

        selected_count = 0
        empties_to_select = []

        if self.helper_set_identifier == "ALL_AIDS":
            empties_to_select = [obj for obj in aids_coll.objects if obj.type == 'EMPTY' and "_Aid" in obj.name]
        else: # Specific set like "1P_Aid", "2P_VP1_Aid", etc.
            empties_to_select = [obj for obj in aids_coll.objects if obj.type == 'EMPTY' and self.helper_set_identifier in obj.name]

        if not empties_to_select:
            self.report({'INFO'}, f"No helpers found for identifier: '{self.helper_set_identifier}'.")
            return {'CANCELLED'}

        active_obj_set = False
        for emp in empties_to_select:
            emp.select_set(True)
            selected_count += 1
            if not active_obj_set: # Make the first one active
                context.view_layer.objects.active = emp
                active_obj_set = True
        
        self.report({'INFO'}, f"Selected {selected_count} helper empties for '{self.helper_set_identifier}'.")
        if context.scene.perspective_tool_settings_splines.show_extraction_helper_lines:
            refresh_extraction_aid_lines(context) # Refresh aid lines based on new selection
        return {'FINISHED'}

class PERSPECTIVE_OT_add_2p_vp2_helpers(bpy.types.Operator):
    """Adds 4 named empties for 2-Point Perspective VP2 extraction."""
    bl_idname = "perspective_splines.add_2p_vp2_helpers"
    bl_label = "Add Helpers for 2P-VP2"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        current_selection = list(context.selected_objects)
        bpy.ops.object.select_all(action='DESELECT')

        base_name = "2P_VP2_Aid" # Different base name for VP2
        # Example positions slightly different from VP1 for distinction
        locs = [Vector((5, -2, 1)), Vector((3, -1, 1)), Vector((5, 2, 1)), Vector((3, 1, 1))]
        suffixes = ["L1_P1", "L1_P2", "L2_P1", "L2_P2"]
        created_empties = []

        for i in range(4):
            name_idx = 1
            unique_name = f"{suffixes[i]}_{base_name}"
            final_name = unique_name
            # Simplified unique naming for this example
            while bpy.data.objects.get(final_name):
                final_name = f"{unique_name}.{str(name_idx).zfill(3)}"
                name_idx += 1
            
            bpy.ops.object.empty_add(type='SPHERE', radius=0.15, align='WORLD', location=locs[i]) # Different shape
            new_empty = context.active_object
            if new_empty:
                new_empty.name = final_name
                new_empty.empty_display_size = 0.5 # Consistent size
                # new_empty.color = (0.5, 1.0, 0.5, 1.0) # Example Greenish for VP2 aids
                for coll in new_empty.users_collection: # Unlink from default collection
                    coll.objects.unlink(new_empty)
                if new_empty.name not in aids_coll.objects: # Link to aids collection
                    aids_coll.objects.link(new_empty)
                new_empty.select_set(True)
                created_empties.append(new_empty)
            else:
                self.report({'WARNING'}, f"Failed to create empty {final_name}")

        if created_empties:
            context.view_layer.objects.active = created_empties[-1]
        else: # Restore original selection if nothing was created
            for obj in current_selection:
                if obj and obj.name in bpy.data.objects:
                     try: obj.select_set(True)
                     except ReferenceError: pass


        self.report({'INFO'}, f"Added 4 helpers for 2P-VP2.")
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if ts and ts.show_extraction_helper_lines:
            refresh_extraction_aid_lines(context)
        return {'FINISHED'}

class PERSPECTIVE_OT_extract_2p_vp2_from_empties(bpy.types.Operator):
    """Extracts and sets VP_2P_2 from 4 selected helper empties."""
    bl_idname = "perspective_splines.extract_2p_vp2_from_empties"
    bl_label = "Set 2P-VP2 from Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if not ts or ts.current_perspective_type != 'TWO_POINT':
            cls.poll_message_set("Switch to 'Two Point' mode.")
            return False
        # Check for specifically named empties for VP2
        selected_empties = [obj for obj in context.selected_objects if obj.type == 'EMPTY' and "2P_VP2_Aid" in obj.name]
        if len(selected_empties) != 4:
            cls.poll_message_set(f"Select 4 '2P_VP2_Aid' empties. Found: {len(selected_empties)}")
            return False
        return True

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        # Sort by name to ensure consistent L1P1, L1P2, L2P1, L2P2 order if names are structured
        selected_empties = sorted(
            [obj for obj in context.selected_objects if obj.type == 'EMPTY' and "2P_VP2_Aid" in obj.name],
            key=lambda o: o.name
        )
        if len(selected_empties) != 4: # Should be caught by poll, but double check
            self.report({'ERROR'}, "Incorrect number of '2P_VP2_Aid' empties selected.")
            return {'CANCELLED'}

        p1_loc = selected_empties[0].matrix_world.translation
        p2_loc = selected_empties[1].matrix_world.translation
        p3_loc = selected_empties[2].matrix_world.translation
        p4_loc = selected_empties[3].matrix_world.translation

        intersection_pt, c1, c2 = line_line_intersection_3d(p1_loc, p2_loc, p3_loc, p4_loc, tolerance=0.05)

        if intersection_pt:
            vp_target_name = VP_TYPE_SPECIFIC_PREFIX_MAP['TWO_POINT'] + "_2" # Target VP_2P_2
            
            PERSPECTIVE_OT_create_2p_vps_if_needed.create_default_two_point_vps(context) # Ensure both VPs and horizon are set up
            main_vp_empty = bpy.data.objects.get(vp_target_name)

            if not main_vp_empty:
                 self.report({'ERROR'}, f"Failed to get or create main VP: {vp_target_name}")
                 return {'CANCELLED'}

            main_vp_empty.location = intersection_pt
            
            update_vp_empty_colors(ts, context)
            
            try:
                # It's usually better to update all lines of that type or specific VP lines
                bpy.ops.perspective_splines.generate_2p_vp2_lines('EXEC_DEFAULT')
                # update_dynamic_horizon_line_curve is called within the generate_2p_... line operators
            except Exception as e:
                self.report({'WARNING'}, f"Error auto-generating VP2 lines: {e}")

            self.report({'INFO'}, f"Set {vp_target_name} to {main_vp_empty.location}. 2P guides for VP2 updated.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Lines for 2P-VP2 do not intersect closely. Adjust '2P_VP2_Aid' empties.")
            return {'CANCELLED'}
        

class PERSPECTIVE_OT_toggle_all_helpers(bpy.types.Operator):
    """Toggles viewport visibility of all helper empties in the aids collection."""
    bl_idname = "perspective_splines.toggle_all_helpers"
    bl_label = "Toggle Helper Empties View" # Clarified label
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        if not aids_coll.objects:
            self.report({'INFO'}, "No helper empties to toggle.")
            return {'CANCELLED'}

        # Determine new hide_viewport state: if any are visible, new state is to hide all.
        # Otherwise, new state is to show all.
        any_currently_visible = any(obj.type == 'EMPTY' and "_Aid" in obj.name and not obj.hide_viewport for obj in aids_coll.objects)
        
        new_hide_state = any_currently_visible # If any visible, we want to hide them.

        changed_count = 0
        for obj in aids_coll.objects:
            if obj.type == 'EMPTY' and "_Aid" in obj.name: # Target only our aid empties
                if obj.hide_viewport != new_hide_state:
                    obj.hide_viewport = new_hide_state
                    changed_count += 1
        
        action_taken = "Hid" if new_hide_state else "Shown"
        self.report({'INFO'}, f"{action_taken} {changed_count} helper empties.")
        
        # Ensure viewport redraws
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}



# Example for PERSPECTIVE_OT_add_2p_vp1_helpers
class PERSPECTIVE_OT_add_2p_vp1_helpers(bpy.types.Operator):
    """Adds 4 named empties for 2-Point Perspective VP1 extraction."""
    bl_idname = "perspective_splines.add_2p_vp1_helpers"
    bl_label = "Add Helpers for 2P-VP1"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        original_active = context.active_object
        original_selection = list(context.selected_objects)
        bpy.ops.object.select_all(action='DESELECT')

        base_name = "2P_VP1_Aid" # Specific to VP1
        # Slightly different default positions for VP1 helpers
        locs = [Vector((-6, -1.5, 1)), Vector((-4, -0.5, 1)), 
                Vector((-6, 1.5, 1)), Vector((-4, 0.5, 1))] 
        suffixes = ["L1_P1", "L1_P2", "L2_P1", "L2_P2"]
        created_empties = []

        for i in range(4):
            unique_name_base = f"{suffixes[i]}_{base_name}"
            final_name = unique_name_base
            name_idx = 1
            while bpy.data.objects.get(final_name): # Ensure unique name
                final_name = f"{unique_name_base}.{str(name_idx).zfill(3)}"
                name_idx += 1
            
            bpy.ops.object.empty_add(type='CUBE', radius=0.1, align='WORLD', location=locs[i]) # Small cubes
            new_empty = context.active_object
            if new_empty:
                new_empty.name = final_name
                new_empty.empty_display_size = 0.2 # Smaller size
                
                # Link to aids_coll and unlink from scene's default collection
                for coll in list(new_empty.users_collection): # Iterate copy
                    coll.objects.unlink(new_empty)
                if new_empty.name not in aids_coll.objects:
                    aids_coll.objects.link(new_empty)
                
                new_empty.select_set(True) # Select it
                created_empties.append(new_empty)
            else:
                self.report({'WARNING'}, f"Failed to create empty {final_name}")
        
        if created_empties:
            context.view_layer.objects.active = created_empties[-1] # Make last one active
        else: # Restore original selection if something went wrong
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj and obj.name in bpy.data.objects:
                    try: obj.select_set(True)
                    except ReferenceError: pass
            if original_active and original_active.name in bpy.data.objects:
                 try: context.view_layer.objects.active = original_active
                 except ReferenceError: pass

        self.report({'INFO'}, f"Added 4 helpers for 2P-VP1.")
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if ts and ts.show_extraction_helper_lines:
            refresh_extraction_aid_lines(context)
        return {'FINISHED'}

# Create PERSPECTIVE_OT_add_2p_vp2_helpers similarly, just change base_name to "2P_VP2_Aid" and default locs

    

class PERSPECTIVE_OT_extract_2p_vp1_from_empties(bpy.types.Operator):
    """Extracts and sets VP_2P_1 from 4 selected helper empties."""
    bl_idname = "perspective_splines.extract_2p_vp1_from_empties"
    bl_label = "Set 2P-VP1 from Selection"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if not ts or ts.current_perspective_type != 'TWO_POINT':
            cls.poll_message_set("Switch to 'Two Point' mode.")
            return False
        selected_empties = [obj for obj in context.selected_objects if obj.type == 'EMPTY' and "2P_VP1_Aid" in obj.name] # Check for specific names
        if len(selected_empties) != 4:
            cls.poll_message_set(f"Select 4 '2P_VP1_Aid' empties. Found: {len(selected_empties)}")
            return False
        return True

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        selected_empties = sorted([obj for obj in context.selected_objects if obj.type == 'EMPTY' and "2P_VP1_Aid" in obj.name], key=lambda o: o.name)
        # Poll ensures we have 4. Sorting helps if selection order wasn't perfect.

        p1_loc = selected_empties[0].matrix_world.translation # L1_P1
        p2_loc = selected_empties[1].matrix_world.translation # L1_P2
        p3_loc = selected_empties[2].matrix_world.translation # L2_P1
        p4_loc = selected_empties[3].matrix_world.translation # L2_P2

        intersection_pt, c1, c2 = line_line_intersection_3d(p1_loc, p2_loc, p3_loc, p4_loc, tolerance=0.05)

        if intersection_pt:
            vp_target_name = VP_TYPE_SPECIFIC_PREFIX_MAP['TWO_POINT'] + "_1"
            main_vp_empty = bpy.data.objects.get(vp_target_name)
            
            # Ensure main 2P VPs exist (this will also handle horizon Z consistency)
            PERSPECTIVE_OT_create_2p_vps_if_needed.create_default_two_point_vps(context)
            main_vp_empty = bpy.data.objects.get(vp_target_name) # Re-fetch in case it was just created

            if not main_vp_empty: # Should be created by the call above
                 self.report({'ERROR'}, f"Failed to get or create main VP: {vp_target_name}")
                 return {'CANCELLED'}

            main_vp_empty.location = intersection_pt
            # Z position of 2P VPs should ideally be the same or controlled by horizon
            # create_default_two_point_vps should handle Z consistency.
            # We might want to force other VPs on the horizon to this Z if the horizon is defined by them.
            # For now, let create_default_two_point_vps and update_dynamic_horizon_line_curve handle it.

            update_vp_empty_colors(ts, context) # Update all VP colors
            
            # Trigger 2P line generation (or at least VP1 specific lines)
            try:
                bpy.ops.perspective_splines.generate_2p_vp1_lines('EXEC_DEFAULT') # This will use the new VP_2P_1 loc
                # update_dynamic_horizon_line_curve is called within generate_2p_vp1_lines
            except Exception as e:
                self.report({'WARNING'}, f"Error auto-generating VP1 lines: {e}")

            self.report({'INFO'}, f"Set {vp_target_name} to {main_vp_empty.location}. 2P guides for VP1 updated.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Lines for 2P-VP1 do not intersect closely. Adjust '2P_VP1_Aid' empties.")
            return {'CANCELLED'}
        

class PERSPECTIVE_OT_add_3p_helpers(bpy.types.Operator):
    """Adds 6 helper empties for 3-Point Perspective extraction (2 for each VP)"""
    bl_idname = "perspective_splines.add_3p_helpers"
    bl_label = "Add 3P Helpers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        bpy.ops.object.select_all(action='DESELECT')
        base_name = "3P_Helper"
        # Positions arbitrarily defined; for actual use, you might let user move these.
        positions = {
            "HVP1_1": Vector((-6, -2, 1)),
            "HVP1_2": Vector((-4, -1, 1)),
            "HVP2_1": Vector((4, -2, 1)),
            "HVP2_2": Vector((6, -1, 1)),
            "VVP_1":  Vector((0, 2, 1)),
            "VVP_2":  Vector((0, 4, 1)),
        }
        created = []
        for key, pos in positions.items():
            unique_name = f"{base_name}_{key}"
            bpy.ops.object.empty_add(type='SINGLE_ARROW', align='WORLD', location=pos)
            new_empty = context.active_object
            if new_empty:
                new_empty.name = unique_name
                new_empty.empty_display_size = 0.5
                for coll in new_empty.users_collection:
                    coll.objects.unlink(new_empty)
                if new_empty.name not in aids_coll.objects:
                    aids_coll.objects.link(new_empty)
                new_empty.select_set(True)
                created.append(new_empty)
        self.report({'INFO'}, f"Added {len(created)} 3P helper empties.")
        if context.scene.perspective_tool_settings_splines.show_extraction_helper_lines:
            refresh_extraction_aid_lines(context)
        return {'FINISHED'}




class PERSPECTIVE_OT_refresh_extraction_aids(bpy.types.Operator):
    """Manually refreshes the visual aid lines based on current selection."""
    bl_idname = "perspective_splines.refresh_extraction_aids"
    bl_label = "Refresh Aid Lines"
    bl_options = {'REGISTER'} # No UNDO needed for a refresh

    from_selection_change: BoolProperty(default=False) # Optional property

    def execute(self, context):
        refresh_extraction_aid_lines(context, from_selection_change=self.from_selection_change)
        self.report({'INFO'}, "Extraction aid lines refreshed.")
        return {'FINISHED'}

class PERSPECTIVE_OT_add_1p_extraction_empties(bpy.types.Operator):
    """Adds 4 named empties for 1-Point Perspective extraction with labeled pair grouping."""
    bl_idname = "perspective_splines.add_1p_extraction_empties"
    bl_label = "Add 4 Helpers for 1P (Front & Back)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        aids_coll = get_extraction_aids_collection(context)
        bpy.ops.object.select_all(action='DESELECT')
        base_name = "1P_Aid"
        # Define positions for front pair and back pair:
        front_pair = [Vector((-2, -2, 0)), Vector((-1, -1, 0))]
        back_pair = [Vector((2, -2, 0)), Vector((1, -1, 0))]
        created_empties = []
        for idx, loc in enumerate(front_pair + back_pair):
            # For clarity, name first two as "Front" and second two as "Back"
            suffix = "Front" if idx < 2 else "Back"
            unique_name = f"{base_name}_{suffix}_{idx+1:03d}"
            bpy.ops.object.empty_add(type='SINGLE_ARROW', align='WORLD', location=loc)
            new_empty = context.active_object
            if new_empty:
                new_empty.name = unique_name
                new_empty.empty_display_size = 0.5
            for coll in new_empty.users_collection:
                coll.objects.unlink(new_empty)
            if new_empty.name not in aids_coll.objects:
                aids_coll.objects.link(new_empty)
                new_empty.select_set(True)
                created_empties.append(new_empty)
            else:
                self.report({'WARNING'}, f"Failed to create empty {unique_name}")
        self.report({'INFO'}, f"Added {len(created_empties)} 1P helper empties (Front & Back).")
        if context.scene.perspective_tool_settings_splines.show_extraction_helper_lines:
            refresh_extraction_aid_lines(context)
        return {'FINISHED'}





class PERSPECTIVE_OT_extract_1p_from_selected_empties(bpy.types.Operator):
    """Extract a 1-Point Vanishing Point from four selected Empty objects.
    Select four empties. The first two define line 1, the next two define line 2.
    The intersection of these lines becomes the 1P Vanishing Point."""
    bl_idname = "perspective_splines.extract_1p_from_empties"
    bl_label = "Extract 1P VP from 4 Empties"
    bl_description = "Select 4 empties (L1_P1, L1_P2, L2_P1, L2_P2). Their intersection sets the 1P VP."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if not ts or ts.current_perspective_type != 'ONE_POINT':
            cls.poll_message_set("Switch to 'One Point' perspective mode first.")
            return False

        selected_empties = [obj for obj in context.selected_objects if obj.type == 'EMPTY']
        if len(selected_empties) != 4:
            cls.poll_message_set(f"Select exactly 4 Empty objects. Found: {len(selected_empties)}")
            return False
        return True

    def execute(self, context):
            ts = context.scene.perspective_tool_settings_splines
            # Mode is already 'ONE_POINT' due to poll

            selected_empties = [obj for obj in context.selected_objects if obj.type == 'EMPTY']
            # Poll already ensures len is 4

            p1_loc = selected_empties[0].matrix_world.translation
            p2_loc = selected_empties[1].matrix_world.translation
            p3_loc = selected_empties[2].matrix_world.translation
            p4_loc = selected_empties[3].matrix_world.translation

            self.report({'INFO'}, f"Line 1: '{selected_empties[0].name}' to '{selected_empties[1].name}'")
            self.report({'INFO'}, f"Line 2: '{selected_empties[2].name}' to '{selected_empties[3].name}'")

            intersection_pt, c1, c2 = line_line_intersection_3d(p1_loc, p2_loc, p3_loc, p4_loc, tolerance=0.05)

            if intersection_pt:
                vp_location_world = intersection_pt
                dist_str = f"{(c1-c2).length:.4f}" if c1 and c2 else "N/A"
                # self.report({'INFO'}, f"Lines intersect near {vp_location_world} (dist: {dist_str}).") # Less verbose report

                vp_name = VP_TYPE_SPECIFIC_PREFIX_MAP['ONE_POINT'] + "_1"
                vp_obj_empty = bpy.data.objects.get(vp_name)

                if not vp_obj_empty:
                    vp_obj_empty = add_vp_empty_if_missing(context, vp_name, vp_location_world, ts.one_point_vp_empty_color)
                else:
                    vp_obj_empty.location = vp_location_world

                # Ensure the horizon_y_level is synced with the new VP's Z before generating lines
                # This is important because generate_one_point will use ts.horizon_y_level
                # and also its own internal logic to sync with the VP.
                if abs(ts.horizon_y_level - vp_location_world.z) > 0.001:
                    ts.horizon_y_level = vp_location_world.z
                    # The update callback for horizon_y_level will call update_dynamic_horizon_line_curve()

                update_vp_empty_colors(ts, context) # Update VP color if it was just created/changed

                # --- ADDED SECTION: Automatically generate/update the 1P lines ---
                try:
                    self.report({'INFO'}, f"VP '{vp_name}' set to {vp_location_world}. Generating lines...")
                    # The generate_one_point operator's create_default_one_point method
                    # will respect the existing VP_1P_1 location.
                    bpy.ops.perspective_splines.generate_one_point('EXEC_DEFAULT')
                except Exception as e:
                    self.report({'ERROR'}, f"VP set, but failed to auto-generate 1P lines: {e}")
                    print(f"Error during auto 1P line generation after VP extraction: {e}")
                    # Decide if this is a critical failure for the operator
                    # return {'CANCELLED'} # Or just continue if setting VP is the primary goal
                # --- END OF ADDED SECTION ---

                # The update_dynamic_horizon_line_curve() is called by ts.horizon_y_level's update
                # and also within generate_one_point's logic, so it should be up-to-date.

                self.report({'INFO'}, f"1P VP '{vp_name}' and lines updated. VP at {vp_location_world}")
                return {'FINISHED'}
            else:
                dist_str = f"{(c1-c2).length:.4f}" if c1 and c2 else "N/A (parallel/collinear)"
                self.report({'ERROR'}, f"Lines defined by empties do not intersect closely enough. Min distance: {dist_str}. Adjust empties.")
                return {'CANCELLED'}



class PERSPECTIVE_OT_clip_guides_to_camera(bpy.types.Operator):
    """Clips each perspective guide so that its endpoints lie exactly on the camera borders."""
    bl_idname = "perspective_splines.clip_guides_to_camera"
    bl_label = "Clip Guides to Camera Borders"
    bl_options = {'REGISTER', 'UNDO'}

    def liang_barsky_clip(self, A, B):
        """
        Liang–Barsky clipping in 2D.
        A and B are 2D tuples representing the projected endpoints (x,y) in normalized camera space.
        Returns (t_min, t_max) such that:
          clipped_point = A + t*(B-A) for t in [t_min, t_max].
        If the line does not cross the unit square, returns None.
        """
        dx = B[0] - A[0]
        dy = B[1] - A[1]
        t_min = 0.0
        t_max = 1.0

        p = [-dx, dx, -dy, dy]
        q = [A[0], 1 - A[0], A[1], 1 - A[1]]

        for i in range(4):
            if p[i] == 0:
                if q[i] < 0:
                    return None  # Parallel and outside
            else:
                r = q[i] / p[i]
                if p[i] < 0:
                    t_min = max(t_min, r)
                else:
                    t_max = min(t_max, r)
                if t_min > t_max:
                    return None  # No intersection
        return t_min, t_max

    def execute(self, context):
        scene = context.scene
        cam = scene.camera
        if not cam:
            self.report({'WARNING'}, "No active camera detected.")
            return {'CANCELLED'}
        
        # Get guides collection (assumes you have a helper function get_guides_collection)
        guides_coll = get_guides_collection(context)
        if not guides_coll:
            self.report({'WARNING'}, "No guides collection found.")
            return {'CANCELLED'}

        trimmed_obj_count = 0

        # Loop over all guide objects in your guides collection (skip the horizon line)
        for obj in guides_coll.objects:
            if obj.type != 'CURVE' or obj.name == "VISUAL_Horizon_Line":
                continue

            curve = obj.data
            change_flag = False
            # Loop over every spline in the curve (assuming your guides are POLY curves with at least 2 points)
            for spline in curve.splines:
                if spline.type != 'POLY' or len(spline.points) < 2:
                    continue

                # Get the endpoints in world space
                pt0_world = obj.matrix_world @ Vector(spline.points[0].co[:3])
                pt1_world = obj.matrix_world @ Vector(spline.points[-1].co[:3])
                
                # Project endpoints to normalized camera space (NDC)
                A_ndc = world_to_camera_view(scene, cam, pt0_world)
                B_ndc = world_to_camera_view(scene, cam, pt1_world)
                
                # Only use the x and y components for 2D clipping
                clip_result = self.liang_barsky_clip((A_ndc.x, A_ndc.y), (B_ndc.x, B_ndc.y))
                if clip_result is None:
                    # If the guide does not cross through the view, you may choose to hide it or set its endpoints to a dummy value.
                    # Here we set both endpoints to the same 0-vector in local space to effectively collapse the guide.
                    spline.points[0].co = (0, 0, 0, 1)
                    spline.points[-1].co = (0, 0, 0, 1)
                    change_flag = True
                else:
                    t_min, t_max = clip_result
                    # Find the new world positions via linear interpolation
                    new_pt0_world = pt0_world + (pt1_world - pt0_world) * t_min
                    new_pt1_world = pt0_world + (pt1_world - pt0_world) * t_max

                    # Convert these world positions back to the object's local space
                    inv_world = obj.matrix_world.inverted()
                    new_pt0_local = inv_world @ new_pt0_world
                    new_pt1_local = inv_world @ new_pt1_world

                    spline.points[0].co = (new_pt0_local.x, new_pt0_local.y, new_pt0_local.z, 1)
                    spline.points[-1].co = (new_pt1_local.x, new_pt1_local.y, new_pt1_local.z, 1)
                    change_flag = True

            if change_flag:
                curve.update_tag()
                trimmed_obj_count += 1

        self.report({'INFO'}, f"Clipped guides in {trimmed_obj_count} object(s).")
        return {'FINISHED'}


class PERSPECTIVE_OT_clear_grid_planes(Operator):
    bl_idname = "perspective_splines.clear_grid_planes"
    bl_label = "Clear Only Grid Planes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = clear_guides_with_prefix(context, ["GridPlane_"])
        self.report({'INFO'}, f"Cleared {count} grid plane objects." if count > 0 else "No grid planes to clear.")
        return {'FINISHED'}
    

class PERSPECTIVE_OT_toggle_guide_visibility(Operator):
    bl_idname = "perspective_splines.toggle_guide_visibility"
    bl_label = "Toggle Guide Group Visibility"
    bl_options = {'REGISTER', 'UNDO'}

    group_prefix: StringProperty(name="Guide Group Prefix")
    # Optional: target_visibility: BoolProperty(name="Target Visibility") # To explicitly set, not just toggle

    def execute(self, context):
        if not self.group_prefix:
            self.report({'WARNING'}, "No guide group prefix specified.")
            return {'CANCELLED'}

        guides_coll = get_guides_collection(context)
        if not guides_coll:
            self.report({'INFO'}, "Guides collection not found.")
            return {'CANCELLED'}

        found_any = False
        # Determine new visibility state: if any are visible, hide all; else show all
        # This is a simple toggle logic. More advanced would use stored states.
        currently_any_visible = False
        for obj in guides_coll.objects:
            if obj.name.startswith(self.group_prefix) and not obj.hide_viewport:
                currently_any_visible = True
                break
        
        new_hide_state = currently_any_visible # If any are visible, new state is to hide them

        for obj in guides_coll.objects:
            if obj.type == 'CURVE' and obj.name.startswith(self.group_prefix):
                obj.hide_viewport = new_hide_state
                found_any = True
        
        if not found_any:
            self.report({'INFO'}, f"No guides found with prefix '{self.group_prefix}'.")
        else:
            action = "Hid" if new_hide_state else "Shown"
            self.report({'INFO'}, f"{action} guides for group '{self.group_prefix}'.")
        
        return {'FINISHED'}

class PERSPECTIVE_OT_create_box_grid(Operator):
    bl_idname = "perspective_splines.create_box_grid"
    bl_label = "Create Perspective Box Grid"
    bl_options = {'REGISTER', 'UNDO'}

    def create_plane_grid(self, context, center, size_u, size_v, subs_u, subs_v,
                          u_axis_vec, v_axis_vec, normal_vec,
                          plane_name_suffix, guides_coll, ts):
        """ Helper to create a single grid plane """
        all_spline_data = []
        half_size_u = size_u / 2.0
        half_size_v = size_v / 2.0

        # Lines along V direction (varying U)
        for i in range(subs_u + 1):
            t = (i / subs_u) - 0.5 # from -0.5 to 0.5
            p_offset = u_axis_vec * (t * size_u)
            pt1 = center + p_offset - (v_axis_vec * half_size_v)
            pt2 = center + p_offset + (v_axis_vec * half_size_v)
            all_spline_data.append([pt1, pt2])

        # Lines along U direction (varying V)
        for i in range(subs_v + 1):
            t = (i / subs_v) - 0.5 # from -0.5 to 0.5
            p_offset = v_axis_vec * (t * size_v)
            pt1 = center + p_offset - (u_axis_vec * half_size_u)
            pt2 = center + p_offset + (u_axis_vec * half_size_u)
            all_spline_data.append([pt1, pt2])
        
        if all_spline_data:
            # Create one object per plane grid for easier management
            grid_obj_name = f"GridPlane_{plane_name_suffix}"
            # Ensure unique name
            idx = 1
            temp_name = grid_obj_name
            while temp_name in bpy.data.objects:
                temp_name = f"{grid_obj_name}.{str(idx).zfill(3)}"
                idx +=1
            grid_obj_name = temp_name

            create_curve_object(context, grid_obj_name, all_spline_data, guides_coll,
                                ts.guide_curves_thickness, ts.guide_curves_opacity)
            return True
        return False

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        guides_coll = get_guides_collection(context)
        clear_guides_with_prefix(context, ["GridPlane_"]) # Clear old grids

        center = Vector(ts.grid_center)
        size = Vector(ts.grid_size)
        subs_u = ts.grid_subdivisions_u
        subs_v = ts.grid_subdivisions_v # Using U for lines along one axis, V for lines along the other for each plane.

        created_any = False

        # Front (+Y) / Back (-Y) : YZ plane, U is Z, V is X
        if ts.grid_draw_front:
            plane_center = center + Vector((0, size.y / 2.0, 0))
            if self.create_plane_grid(context, plane_center, size.z, size.x, subs_v, subs_u, 
                                 Vector((0,0,1)), Vector((1,0,0)), Vector((0,1,0)), "Front", guides_coll, ts):
                created_any = True
        if ts.grid_draw_back:
            plane_center = center - Vector((0, size.y / 2.0, 0))
            if self.create_plane_grid(context, plane_center, size.z, size.x, subs_v, subs_u, 
                                 Vector((0,0,1)), Vector((1,0,0)), Vector((0,-1,0)), "Back", guides_coll, ts):
                created_any = True
        
        # Top (+Z) / Bottom (-Z) : XY plane, U is X, V is Y
        if ts.grid_draw_top:
            plane_center = center + Vector((0,0, size.z / 2.0))
            if self.create_plane_grid(context, plane_center, size.x, size.y, subs_u, subs_v,
                                 Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1)), "Top", guides_coll, ts):
                created_any = True
        if ts.grid_draw_bottom:
            plane_center = center - Vector((0,0, size.z / 2.0))
            if self.create_plane_grid(context, plane_center, size.x, size.y, subs_u, subs_v,
                                 Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,-1)), "Bottom", guides_coll, ts):
                created_any = True

        # Right (+X) / Left (-X) : XZ plane (careful, Blender's XZ is often Y up), let's say YZ plane, U is Y, V is Z
        # For side views, let's use YZ plane where U is Y, V is Z.
        if ts.grid_draw_right: # +X side
            plane_center = center + Vector((size.x / 2.0, 0, 0))
            if self.create_plane_grid(context, plane_center, size.y, size.z, subs_u, subs_v, # U along Y, V along Z
                                 Vector((0,1,0)), Vector((0,0,1)), Vector((1,0,0)), "Right", guides_coll, ts):
                 created_any = True
        if ts.grid_draw_left: # -X side
            plane_center = center - Vector((size.x / 2.0, 0, 0))
            if self.create_plane_grid(context, plane_center, size.y, size.z, subs_u, subs_v,
                                 Vector((0,1,0)), Vector((0,0,1)), Vector((-1,0,0)), "Left", guides_coll, ts):
                created_any = True

        if created_any:
            self.report({'INFO'}, "Generated grid plane(s).")
        else:
            self.report({'INFO'}, "No grid planes selected for drawing.")
        return {'FINISHED'}    

class PERSPECTIVE_OT_merge_specific_guides(Operator):
    bl_idname = "perspective_splines.merge_specific_guides"
    bl_label = "Merge Specific Perspective Guides"
    bl_options = {'REGISTER', 'UNDO'}

    group_identifier: StringProperty(
        name="Guide Group Identifier",
        description="Identifier for the group of guides to merge (e.g., 2P_VP1, ALL_CURRENT_TYPE)",
        default="ALL_SCENE_GUIDES_FALLBACK" # Default to merging all if no specific group given
    )

    # This dictionary maps a 'group_identifier' to:
    # 1. A tuple of prefixes to identify the curves for that group.
    # 2. A suggested suffix for the merged object's name.
    # This will be populated dynamically or used with perspective-type specific sub-mappings.
    
    # Structure: PERSPECTIVE_TYPE_KEY: { GROUP_NAME_FOR_UI: ( (PREFIX1, PREFIX2, ...), "MergedNameSuffix" ) }
    GUIDE_GROUP_DEFS = {
        'ONE_POINT': {
            'MAIN_LINES': (("1P_Guides",), "1P_Lines")
        },
        'TWO_POINT': {
            'VP1_LINES': (("2P_Guides_VP1",), "2P_VP1_Lines"),
            'VP2_LINES': (("2P_Guides_VP2",), "2P_VP2_Lines"),
            'VERTICAL_LINES': (("2P_Guides_Vertical",), "2P_Vertical_Lines")
        },
        'THREE_POINT': {
            'H1_LINES': (("3P_Guides_H1",), "3P_H1_Lines"),
            'H2_LINES': (("3P_Guides_H2",), "3P_H2_Lines"),
            'V_LINES': (("3P_Guides_V",), "3P_V_Lines")
        },
        'FISH_EYE': {
            # FE guides might be FE_Guides_Lon_X or FE_Guides_Lat_X or just FE_Guides_X
            'LONGITUDE_LINES': (("FE_Guides_Lon",), "FE_Longitude_Lines"), # Specific if you named them like this
            'LATITUDE_LINES': (("FE_Guides_Lat",), "FE_Latitude_Lines"),   # Specific if you named them like this
            'ALL_FE_LINES': (("FE_Guides",), "FE_All_Lines") # General prefix for all FE guides
        }
    }


    @classmethod
    def poll(cls, context):
        guides_coll = get_guides_collection(context)
        return guides_coll and any(o.type == 'CURVE' and o.name != HORIZON_CURVE_OBJ_NAME for o in guides_coll.objects)

    def get_curves_for_group(self, context, guides_coll):
        tool_settings = context.scene.perspective_tool_settings_splines
        current_perspective_type = tool_settings.current_perspective_type
        
        curves_to_process = []
        target_prefixes = []
        merged_name_suffix = "Guides" # Default suffix

        if self.group_identifier == "ALL_SCENE_GUIDES_FALLBACK":
            # Collect all known guide prefixes regardless of type for a true "merge all"
            all_known_prefixes = set()
            for type_key, groups in self.GUIDE_GROUP_DEFS.items():
                for group_key, (prefixes, _) in groups.items():
                    all_known_prefixes.update(prefixes)
            if not all_known_prefixes: # Fallback if GUIDE_GROUP_DEFS is empty somehow
                 all_known_prefixes = ("1P_Guides", "2P_Guides_", "3P_Guides_", "FE_Guides_")

            target_prefixes = tuple(all_known_prefixes)
            merged_name_suffix = "All_Scene_Guides"

        elif self.group_identifier == "ALL_CURRENT_TYPE":
            if current_perspective_type != 'NONE' and current_perspective_type in self.GUIDE_GROUP_DEFS:
                current_type_defs = self.GUIDE_GROUP_DEFS[current_perspective_type]
                all_type_prefixes = set()
                for _, (prefixes, _) in current_type_defs.items():
                    all_type_prefixes.update(prefixes)
                target_prefixes = tuple(all_type_prefixes)
                merged_name_suffix = f"{current_perspective_type.replace('_','')}All_Guides"
            else: # No specific type or no defs for it
                return [], "Guides_NoType"

        else: # Specific group for the current type (e.g., "2P_VP1_LINES")
            if current_perspective_type != 'NONE' and current_perspective_type in self.GUIDE_GROUP_DEFS:
                current_type_defs = self.GUIDE_GROUP_DEFS[current_perspective_type]
                # The group_identifier should directly match a key in current_type_defs
                # e.g. group_identifier = "VP1_LINES" for perspective_type 'TWO_POINT'
                if self.group_identifier in current_type_defs:
                    prefixes_tuple, suffix_from_def = current_type_defs[self.group_identifier]
                    target_prefixes = prefixes_tuple
                    merged_name_suffix = suffix_from_def
                else: # Identifier not found for current type
                    return [], f"UnknownGroup_{self.group_identifier}"
            else: # No type selected for specific group
                return [], f"Guides_NoType_For_{self.group_identifier}"

        if not target_prefixes:
            return [], "NoPrefixes"

        for obj in guides_coll.objects:
            if obj.type == 'CURVE' and obj.name != HORIZON_CURVE_OBJ_NAME:
                for prefix in target_prefixes:
                    if obj.name.startswith(prefix):
                        curves_to_process.append(obj)
                        break # Object matched, move to next object
        
        return curves_to_process, merged_name_suffix


    def execute(self, context):
        guides_coll = get_guides_collection(context)
        if not guides_coll:
            self.report({'INFO'}, "Guides collection not found.")
            return {'CANCELLED'}

        curves_to_merge, base_name_suffix = self.get_curves_for_group(context, guides_coll)

        if not curves_to_merge:
            self.report({'INFO'}, f"No guide curves found for group identifier: '{self.group_identifier}'.")
            return {'CANCELLED'}

        if len(curves_to_merge) < 2:
            self.report({'INFO'}, f"Only {len(curves_to_merge)} curve(s) found for '{self.group_identifier}'. No merge needed or possible.")
            if curves_to_merge: # If one, select it
                bpy.ops.object.select_all(action='DESELECT')
                try:
                    curves_to_merge[0].select_set(True)
                    context.view_layer.objects.active = curves_to_merge[0]
                except ReferenceError:
                    self.report({'WARNING'}, "The single curve found no longer exists.")
                    return {'CANCELLED'}
            return {'FINISHED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        original_active = context.view_layer.objects.active
        original_selection = list(context.selected_objects) # Make a copy
        
        bpy.ops.object.select_all(action='DESELECT')
        valid_curves_for_join = []
        for obj in curves_to_merge:
            if obj.name in bpy.data.objects: # Check if object still exists
                obj.select_set(True)
                valid_curves_for_join.append(obj)
            else:
                print(f"Info: Object '{obj.name}' for merge group '{self.group_identifier}' no longer exists.")
        
        if len(valid_curves_for_join) < 2:
            self.report({'INFO'}, f"Not enough valid curves ({len(valid_curves_for_join)}) remaining to merge for '{self.group_identifier}'.")
            # Restore original selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj_sel in original_selection:
                if obj_sel and obj_sel.name in bpy.data.objects:
                    try: obj_sel.select_set(True)
                    except ReferenceError: pass
            if original_active and original_active.name in bpy.data.objects:
                try: context.view_layer.objects.active = original_active
                except ReferenceError: pass
            return {'CANCELLED'}
            
        context.view_layer.objects.active = valid_curves_for_join[0]

        try:
            bpy.ops.object.join()
        except RuntimeError as e:
            self.report({'ERROR'}, f"Merge failed for group '{self.group_identifier}': {e}")
            # Restore original selection attempt
            bpy.ops.object.select_all(action='DESELECT')
            for obj_sel in original_selection:
                if obj_sel and obj_sel.name in bpy.data.objects:
                   try: obj_sel.select_set(True)
                   except ReferenceError: pass
            if original_active and original_active.name in bpy.data.objects:
                try: context.view_layer.objects.active = original_active
                except ReferenceError: pass
            return {'CANCELLED'}
        
        merged_obj = context.active_object
        if merged_obj:
            # Create a unique name for the merged object
            final_name_base = f"Merged_{base_name_suffix}"
            current_name_to_check = final_name_base
            idx = 1
            while current_name_to_check in bpy.data.objects and bpy.data.objects[current_name_to_check] != merged_obj:
                current_name_to_check = f"{final_name_base}.{str(idx).zfill(3)}"
                idx += 1
            merged_obj.name = current_name_to_check
            self.report({'INFO'}, f"Merged {len(valid_curves_for_join)} guides for '{self.group_identifier}' into: {merged_obj.name}")
        else:
            self.report({'WARNING'}, "Merge did not result in an active object.")
            # Restore selection might be complex here if join partly failed.
            return {'CANCELLED'}

        return {'FINISHED'}


# --- Keep your existing PERSPECTIVE_OT_merge_guides if you want a simple "Merge All in Collection" button ---
# OR remove it if PERSPECTIVE_OT_merge_specific_guides with "ALL_SCENE_GUIDES_FALLBACK" covers its need.
# For now, let's assume you might want to keep it as a distinct "merge all visible guides".

class PERSPECTIVE_OT_merge_guides(Operator): # This is your existing "Merge Guides Only"
    bl_idname = "perspective_splines.merge_guides"
    bl_label = "Merge All Visible Guides" # Renamed label for clarity if keeping both merge ops
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        guides_coll = get_guides_collection(context)
        curves_to_merge = [
            o for o in guides_coll.objects 
            if o.type == 'CURVE' and o.data and o.data.splines and o.name != HORIZON_CURVE_OBJ_NAME
        ]
        if not curves_to_merge:
            self.report({'INFO'}, "No guide curves found to merge.")
            return {'CANCELLED'}
        
        if len(curves_to_merge) < 2:
            self.report({'INFO'}, "Only one guide curve present. No merge needed.")
            if curves_to_merge: # Select the single curve
                bpy.ops.object.select_all(action='DESELECT')
                try:
                    curves_to_merge[0].select_set(True)
                    context.view_layer.objects.active = curves_to_merge[0]
                except ReferenceError: pass
            return {'FINISHED'} # Or CANCELLED

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        original_active = context.view_layer.objects.active
        original_selection = list(context.selected_objects) 
        bpy.ops.object.select_all(action='DESELECT')
        
        valid_curves_for_join = []
        for obj in curves_to_merge:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
                valid_curves_for_join.append(obj)
        
        if len(valid_curves_for_join) < 2:
            self.report({'INFO'}, "Not enough valid curves remaining to merge.")
            # Restore original selection
            # ... (similar restoration as in merge_specific_guides) ...
            return {'CANCELLED'}
            
        context.view_layer.objects.active = valid_curves_for_join[0]

        try:
            bpy.ops.object.join()
        except RuntimeError as e:
            self.report({'ERROR'}, f"Merge all guides failed: {e}")
            # ... (similar restoration) ...
            return {'CANCELLED'}
        
        merged_obj = context.active_object
        if merged_obj:
            base_name = "Merged_All_Guides"
            current_name_to_check = base_name
            idx = 1
            while current_name_to_check in bpy.data.objects and bpy.data.objects[current_name_to_check] != merged_obj:
                current_name_to_check = f"{base_name}.{str(idx).zfill(3)}"
                idx += 1
            merged_obj.name = current_name_to_check
            self.report({'INFO'}, f"Merged all guides into object: {merged_obj.name}")
        else:
            self.report({'WARNING'}, "Merge all operation did not result in an active object.")
            return {'CANCELLED'}
        return {'FINISHED'}


class PERSPECTIVE_OT_merge_guides(Operator):
    bl_idname = "perspective_splines.merge_guides"
    bl_label = "Merge Guides Only"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        guides_coll = get_guides_collection(context)
        # Select all curve objects in the guides collection (except the horizon curve)
        curves_to_merge = [o for o in guides_coll.objects 
                           if o.type == 'CURVE' and o.data and o.data.splines and o.name != HORIZON_CURVE_OBJ_NAME]
        if not curves_to_merge:
            self.report({'INFO'}, "No guide curves found to merge.")
            return {'CANCELLED'}
        
        # Ensure we are in Object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        original_active = context.view_layer.objects.active
        original_selection = list(context.selected_objects) # Make a copy
        bpy.ops.object.select_all(action='DESELECT')
        
        for obj in curves_to_merge:
            obj.select_set(True)
        
        if not curves_to_merge: # Should be caught earlier, but as a safeguard
            bpy.ops.object.select_all(action='DESELECT') # Restore selection
            for obj in original_selection:
                if obj and obj.name in bpy.data.objects: # Check if obj still exists
                   try: obj.select_set(True)
                   except ReferenceError: pass
            context.view_layer.objects.active = original_active
            self.report({'ERROR'}, "No curves were selected for merging.")
            return {'CANCELLED'}
            
        context.view_layer.objects.active = curves_to_merge[0]

        try:
            bpy.ops.object.join()
        except RuntimeError as e:
            self.report({'ERROR'}, f"Merge failed: {e}")
            # Restore selection before returning
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj and obj.name in bpy.data.objects:
                   try: obj.select_set(True)
                   except ReferenceError: pass
            context.view_layer.objects.active = original_active
            return {'CANCELLED'}
        
        merged_obj = context.active_object
        if merged_obj:
            self.report({'INFO'}, f"Merged guides into object: {merged_obj.name}")
        else:
            self.report({'WARNING'}, "Merge operation did not result in an active object.")
            # Attempt to restore selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj and obj.name in bpy.data.objects:
                   try: obj.select_set(True)
                   except ReferenceError: pass
            context.view_layer.objects.active = original_active
            return {'CANCELLED'}


        # Restore original selection (optional, but good practice if they weren't part of the merge)
        # For this operator, the merged object becomes the new selection.
        # If you want to restore the previous broader selection, uncomment:
        # bpy.ops.object.select_all(action='DESELECT')
        # for obj in original_selection:
        #     if obj and obj.name in bpy.data.objects and obj.name != merged_obj.name:
        #         try: obj.select_set(True)
        #         except ReferenceError: pass
        # if merged_obj and merged_obj.name in bpy.data.objects: # Ensure merged object remains selected
        #    merged_obj.select_set(True)
        #    context.view_layer.objects.active = merged_obj
        # else:
        #    context.view_layer.objects.active = original_active

        return {'FINISHED'}



# ... (Rest of your operators: PERSPECTIVE_OT_generate_horizon_spline, etc. down to PERSPECTIVE_OT_convert_to_grease_pencil)

class PERSPECTIVE_OT_generate_horizon_spline(Operator):
    bl_idname = "perspective_splines.generate_horizon"
    bl_label = "Create/Set Horizon Ctrl & Visual"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        tool_settings = context.scene.perspective_tool_settings_splines
        helpers_coll = get_helpers_collection(context)
        horizon_ctrl = get_horizon_control_object()
        if not horizon_ctrl:
            horizon_ctrl = bpy.data.objects.new(HORIZON_CTRL_OBJ_NAME, None)
            helpers_coll.objects.link(horizon_ctrl)
            horizon_ctrl.empty_display_type = 'CIRCLE'
            horizon_ctrl.empty_display_size = 0.5
        horizon_ctrl.location = Vector((0, 0, tool_settings.horizon_y_level))

        horizon_curve_obj = get_horizon_curve_object()
        if not horizon_curve_obj:
            guides_coll = get_guides_collection(context)
            hz_len = tool_settings.horizon_line_length / 2.0
            # Points for the horizon curve visual should be relative to its object origin (0,0,0)
            # The update_dynamic_horizon_line_curve function handles setting world space coords.
            # For initial creation, we can use simple points, they will be updated.
            pts = [Vector((-hz_len, 0, 0)), Vector((hz_len, 0, 0))]
            col = list(tool_settings.horizon_line_color) # Get the RGBA color from settings
            horizon_curve_obj = create_curve_object(context, HORIZON_CURVE_OBJ_NAME, [pts], guides_coll,
                                        bevel_depth=tool_settings.horizon_line_thickness,
                                        opacity=col[3], color_rgb=col[:3]) # Pass opacity and color_rgb separately
            if not horizon_curve_obj:
                self.report({'ERROR'}, "Failed to create horizon visual line.")
                return {'CANCELLED'}
            # Position the curve object itself at the horizon Z, though update_dynamic... might override
            # horizon_curve_obj.location.z = tool_settings.horizon_y_level 
            # Actually, update_dynamic_horizon_line_curve expects it at world origin if it's placing VPs directly.
            # For 1P, it effectively re-centers it. So (0,0,0) is fine.

        update_dynamic_horizon_line_curve(context) # This will correctly position/shape it
        self.report({'INFO'}, f"Horizon elements set. Ctrl Z: {tool_settings.horizon_y_level:.2f}")
        return {'FINISHED'}

class PERSPECTIVE_OT_add_vanishing_point_empty(Operator):
    bl_idname = "perspective_splines.add_vp_empty"
    bl_label = "Add Generic VP Empty"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        tool_settings = context.scene.perspective_tool_settings_splines
        prefix = VP_PREFIX + "Custom" # Default for generic
        if tool_settings.current_perspective_type in VP_TYPE_SPECIFIC_PREFIX_MAP:
            prefix = VP_TYPE_SPECIFIC_PREFIX_MAP[tool_settings.current_perspective_type]

        num = 1
        while f"{prefix}_Generic_{num}" in bpy.data.objects: num += 1
        vp_name = f"{prefix}_Generic_{num}"
        vp_obj = add_vp_empty_if_missing(context, vp_name, context.scene.cursor.location.copy(), empty_color=(0.7,0.7,0.7,1.0)) # Pass empty_color
        vp_obj.empty_display_type = 'CUBE' # Differentiate generic
        self.report({'INFO'}, f"Added generic VP: {vp_name}")
        try:
            update_dynamic_horizon_line_curve(context)
            update_vp_empty_colors(tool_settings, context)
        except Exception as e: print(f"Error in updates post add_vp_empty: {e}")
        return {'FINISHED'}

class PERSPECTIVE_OT_remove_selected_helper_empty(Operator):
    bl_idname = "perspective_splines.remove_selected_helper_empty"
    bl_label = "Remove Selected Helper"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        act_obj = context.active_object
        return act_obj and act_obj.type == 'EMPTY' and \
               (act_obj.name.startswith(VP_PREFIX) or act_obj.name == HORIZON_CTRL_OBJ_NAME)
    def execute(self, context):
        obj_to_remove = context.active_object
        name = obj_to_remove.name
        is_hz_ctrl = (name == HORIZON_CTRL_OBJ_NAME)
        try: bpy.data.objects.remove(obj_to_remove, do_unlink=True)
        except: pass # Ignore if already gone
        if is_hz_ctrl:
            try: bpy.ops.perspective_splines.clear_horizon('EXEC_DEFAULT')
            except Exception as e: print(f"Error clearing horizon after ctrl removal: {e}")
        try: update_dynamic_horizon_line_curve(context)
        except Exception as e: print(f"Error updating horizon after helper removal: {e}")
        self.report({'INFO'}, f"Removed helper: {name}.")
        return {'FINISHED'}

class PERSPECTIVE_OT_clear_type_guides_splines(Operator):
    bl_idname = "perspective_splines.clear_type_guides"
    bl_label = "Clear Type VPs & Lines"
    bl_options = {'REGISTER', 'UNDO'}
    type_filter_prop: StringProperty(name="Type to Clear", default="")

    def execute(self, context):
        tool_settings = context.scene.perspective_tool_settings_splines
        type_key = self.type_filter_prop if self.type_filter_prop else tool_settings.current_perspective_type # Fallback to current if no prop
        
        print(f"--- PERSPECTIVE_OT_clear_type_guides_splines: Attempting to clear for type_key: '{type_key}' ---") # DEBUG

        if type_key == 'NONE' and not self.type_filter_prop: # If type_key is genuinely NONE from current mode and no filter_prop
            self.report({'INFO'}, "No specific perspective type active to clear.")
            print("  DEBUG clear_type_guides: Type is NONE and no filter_prop, nothing to clear here.") # DEBUG
            return {'CANCELLED'}
        
        vp_prefixes_remove, guide_prefixes_clear = [], []
        if type_key == 'ONE_POINT':
            vp_prefixes_remove.append(VP_TYPE_SPECIFIC_PREFIX_MAP['ONE_POINT'])
            guide_prefixes_clear.append("1P_Guides")
        elif type_key == 'TWO_POINT':
            vp_prefixes_remove.append(VP_TYPE_SPECIFIC_PREFIX_MAP['TWO_POINT'])
            guide_prefixes_clear.extend(["2P_Guides_VP1", "2P_Guides_VP2", "2P_Guides_Vertical"])
        elif type_key == 'THREE_POINT':
            vp_prefixes_remove.append(VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_H'])
            vp_prefixes_remove.append(VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_V'])
            guide_prefixes_clear.extend(["3P_Guides_H1", "3P_Guides_H2", "3P_Guides_V"])
        elif type_key == 'FISH_EYE':
            vp_prefixes_remove.append(VP_TYPE_SPECIFIC_PREFIX_MAP['FISH_EYE'])
            guide_prefixes_clear.append("FE_Guides")
        else:
            print(f"  DEBUG clear_type_guides: Unknown type_key '{type_key}', no VP prefixes defined for clearing.") # DEBUG
            # No VPs to clear based on unknown type, but still try to clear general guides if any were associated
            # This path should ideally not be taken if type_key is always valid from the enum.

        helpers_collection = get_helpers_collection(context)
        all_vps_in_helpers = [obj for obj in helpers_collection.objects if obj.type == 'EMPTY' and obj.name.startswith(VP_PREFIX)]
        
        print(f"  DEBUG clear_type_guides: Found VPs in helpers_collection: {[vp.name for vp in all_vps_in_helpers]}") # DEBUG
        print(f"  DEBUG clear_type_guides: Target VP prefixes for removal: {vp_prefixes_remove}") # DEBUG
        
        vps_removed_count = 0
        for prefix_to_remove in vp_prefixes_remove:
            print(f"    DEBUG clear_type_guides: Processing prefix: '{prefix_to_remove}'") # DEBUG
            for vp in list(all_vps_in_helpers): # Iterate a copy if modifying the source list (though remove from bpy.data)
                if vp.name in bpy.data.objects: # Check if it wasn't already removed
                    if vp.name.startswith(prefix_to_remove):
                        print(f"      DEBUG clear_type_guides: MATCH! Attempting to remove VP: {vp.name}") # DEBUG
                        try:
                            bpy.data.objects.remove(vp, do_unlink=True)
                            vps_removed_count +=1
                            # We might need to remove it from all_vps_in_helpers if we iterate it multiple times,
                            # but since we iterate bpy.data.objects it should be fine.
                        except Exception as e:
                            print(f"      DEBUG clear_type_guides: Error removing {vp.name}: {e}")
        
        guides_cleared_count = 0
        if guide_prefixes_clear:
            print(f"  DEBUG clear_type_guides: Guide prefixes to clear: {guide_prefixes_clear}") # DEBUG
            guides_cleared_count = clear_guides_with_prefix(context, guide_prefixes_clear)
        
        try:
            update_dynamic_horizon_line_curve(context)
        except Exception as e:
            print(f"  Error updating horizon after type clear: {e}")
            
        self.report({'INFO'}, f"Cleared {vps_removed_count} VPs & {guides_cleared_count} guide groups for: {type_key}.")
        print(f"--- PERSPECTIVE_OT_clear_type_guides_splines: Finished for '{type_key}' ---") # DEBUG
        return {'FINISHED'}


class PERSPECTIVE_OT_clear_just_guides(Operator):
    bl_idname = "perspective_splines.clear_just_guides"
    bl_label = "Clear ONLY Guide Lines"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        prefixes = ["1P_Guides", "2P_Guides_VP1", "2P_Guides_VP2", "2P_Guides_Vertical",
                    "3P_Guides_H1", "3P_Guides_H2", "3P_Guides_V", "FE_Guides"]
        count = clear_guides_with_prefix(context, prefixes)
        self.report({'INFO'}, f"Cleared {count} guide objects." if count > 0 else "No guides to clear.")
        return {'FINISHED'}

class PERSPECTIVE_OT_clear_horizon_spline(Operator):
    bl_idname = "perspective_splines.clear_horizon"
    bl_label = "Clear Horizon Elements"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        cleared = 0
        hz_ctrl = get_horizon_control_object()
        if hz_ctrl:
            try: bpy.data.objects.remove(hz_ctrl, do_unlink=True); cleared+=1
            except: pass
        hz_curve = get_horizon_curve_object()
        if hz_curve:
            try:
                if hz_curve.data and hz_curve.data.name in bpy.data.curves and hz_curve.data.users <=1:
                    bpy.data.curves.remove(hz_curve.data)
                bpy.data.objects.remove(hz_curve, do_unlink=True); cleared+=1
            except: pass
        self.report({'INFO'}, "Horizon elements cleared." if cleared > 0 else "No horizon elements to clear.")
        try: update_dynamic_horizon_line_curve(context) # Should effectively hide it
        except Exception as e: print(f"Error updating horizon after clear_horizon: {e}")
        return {'FINISHED'}

class PERSPECTIVE_OT_clear_all_perspective_splines(Operator):
    bl_idname = "perspective_splines.clear_all"
    bl_label = "Clear ALL Perspective Helpers"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        print("Attempting to clear ALL perspective data...")
        for vp in get_vanishing_points(): # Get all VPs regardless of type
            try: bpy.data.objects.remove(vp, do_unlink=True)
            except Exception as e: print(f"  Failed to remove VP {vp.name}: {e}")
        try: bpy.ops.perspective_splines.clear_horizon('EXEC_DEFAULT')
        except Exception as e: print(f"  Failed to clear horizon elements: {e}")
        all_guide_prefixes = ["1P_Guides", "2P_Guides_VP1", "2P_Guides_VP2", "2P_Guides_Vertical",
                              "3P_Guides_H1", "3P_Guides_H2", "3P_Guides_V", "FE_Guides"]
        clear_guides_with_prefix(context, all_guide_prefixes)
        try: update_dynamic_horizon_line_curve(context)
        except Exception as e: print(f"  Error updating horizon post clear all: {e}")
        self.report({'INFO'}, "Cleared ALL perspective data.")
        return {'FINISHED'}

class PERSPECTIVE_OT_generate_one_point_splines(Operator):
    bl_idname = "perspective_splines.generate_one_point"
    bl_label = "Generate 1P Lines"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def create_default_one_point(cls, context):
        print("DEBUG: create_default_one_point CALLED") 
        ts = context.scene.perspective_tool_settings_splines
        vp_name_1p = VP_TYPE_SPECIFIC_PREFIX_MAP['ONE_POINT'] + "_1"
        
        existing_vp = bpy.data.objects.get(vp_name_1p)
        initial_loc_for_new = Vector((0.0, 0.0, ts.horizon_y_level)) 
        horizon_ctrl = get_horizon_control_object()
        if horizon_ctrl: 
            initial_loc_for_new.z = horizon_ctrl.location.z
            # initial_loc_for_new.x = horizon_ctrl.location.x # Optional
            # initial_loc_for_new.y = horizon_ctrl.location.y # Optional

        current_vp_location = initial_loc_for_new
        if existing_vp:
            current_vp_location = existing_vp.location # Preserve existing location if VP found

        # This will create if not existing, or update color/collection if it does
        vp_1p_obj = add_vp_empty_if_missing(context, vp_name_1p, current_vp_location, ts.one_point_vp_empty_color)

        if vp_1p_obj: # Re-fetch or use returned object
            if not existing_vp: # If it was newly created
                 vp_1p_obj.location = initial_loc_for_new # Ensure new ones get the default
                 print(f"DEBUG create_default_one_point: VP '{vp_name_1p}' created at {initial_loc_for_new}.")
            else:
                 print(f"DEBUG create_default_one_point: VP '{vp_name_1p}' found/ensured at {vp_1p_obj.location}.")

            # Sync horizon_y_level to the VP_1P_1's Z
            if abs(ts.horizon_y_level - vp_1p_obj.location.z) > 0.001:
                print(f"DEBUG create_default_one_point: Syncing horizon_y_level from {ts.horizon_y_level} to VP_1P_1.z {vp_1p_obj.location.z}")
                ts.horizon_y_level = vp_1p_obj.location.z 
        else:
            print(f"DEBUG create_default_one_point: CRITICAL - VP '{vp_name_1p}' could not be assured.")
    
    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        vps_check = get_vanishing_points('ONE_POINT')
        
        if not get_horizon_control_object() and not vps_check:
            try:
                bpy.ops.perspective_splines.generate_horizon('EXEC_DEFAULT')
            except Exception as e:
                print(f"Error ensuring horizon for 1P (no VP, no HC): {e}")

        PERSPECTIVE_OT_generate_one_point_splines.create_default_one_point(context)
        
        vps = get_vanishing_points('ONE_POINT') 
        if not vps:
            self.report({'ERROR'}, "1P VP not found or could not be created.")
            return {'CANCELLED'}
        
        if abs(ts.horizon_y_level - vps[0].location.z) > 0.001 :
             ts.horizon_y_level = vps[0].location.z 

        try: update_vp_empty_colors(ts, context)
        except Exception as e: print(f"Error updating VP colors for 1P: {e}")
        
        guides_coll = get_guides_collection(context)
        clear_guides_with_prefix(context, ["1P_Guides"]) # Clear existing 1P guides
        vp_loc = vps[0].location.copy()
        spline_data = []
        ext = ts.one_point_line_extension

        if ts.one_point_draw_radial:
            spline_data.extend(generate_radial_lines_in_plane(vp_loc, ts.one_point_grid_density_radial, ext, 'XZ'))
        
        if ts.one_point_draw_ortho_x:
            half_grid_world_extent_x = ts.one_point_grid_extent * ext * 0.5 
            vertical_spacing_world = ts.one_point_grid_extent * ext * 0.2 
            density_x = ts.one_point_grid_density_ortho_x
            for i in range(density_x + 1):
                off_z_factor = (i / density_x - 0.5) * 2.0 if density_x > 0 else 0 
                curr_z = vp_loc.z + off_z_factor * (vertical_spacing_world / 2.0)
                spline_data.append([
                    Vector((vp_loc.x - half_grid_world_extent_x, vp_loc.y, curr_z)),
                    Vector((vp_loc.x + half_grid_world_extent_x, vp_loc.y, curr_z))
                ])
        
        if ts.one_point_draw_ortho_y:
            half_grid_world_extent_z = ts.one_point_grid_extent * ext * 0.5 
            horizontal_spacing_world = ts.one_point_grid_extent * ext * 0.2 
            density_y = ts.one_point_grid_density_ortho_y
            for i in range(density_y + 1):
                off_x_factor = (i / density_y - 0.5) * 2.0 if density_y > 0 else 0
                curr_x = vp_loc.x + off_x_factor * (horizontal_spacing_world / 2.0)
                spline_data.append([
                    Vector((curr_x, vp_loc.y, vp_loc.z - half_grid_world_extent_z)),
                    Vector((curr_x, vp_loc.y, vp_loc.z + half_grid_world_extent_z))
                ])

        if not spline_data:
            self.report({'INFO'}, "No 1P lines to generate based on current settings.")
            try: update_dynamic_horizon_line_curve(context)
            except Exception as e: print(f"Error updating horizon (no 1P lines generated): {e}")
            return {'FINISHED'}

        # <<<< MODIFICATION IS HERE >>>>
        opac = ts.guide_curves_opacity # Get global opacity from settings
        thickness = ts.guide_curves_thickness # Get global thickness
        created_count = 0
        for i, pts_list in enumerate(spline_data): 
            # Call create_curve_object WITHOUT the color_rgb argument
            if create_curve_object(context, f"1P_Guides_{i+1}", [pts_list], guides_coll,
                                thickness, opac): # Pass thickness and opacity
                created_count +=1
        # <<<< END OF MODIFICATION >>>>
                                
        self.report({'INFO'}, f"Generated {created_count} 1P line objects.")
        try: update_dynamic_horizon_line_curve(context)
        except Exception as e: print(f"Error updating horizon after 1P gen: {e}")
        return {'FINISHED'}


# (Place these after PERSPECTIVE_OT_generate_one_point_splines)

class PERSPECTIVE_OT_create_2p_vps_if_needed(Operator):
    """Helper to ensure 2P VPs exist, called by specific 2P line generators."""
    bl_idname = "perspective_splines.create_2p_vps_if_needed"
    bl_label = "Ensure 2P VPs"
    bl_options = {'REGISTER', 'INTERNAL'}

# Inside class PERSPECTIVE_OT_create_2p_vps_if_needed(Operator):
    # Inside class PERSPECTIVE_OT_create_2p_vps_if_needed(Operator):

    @classmethod
    def create_default_two_point_vps(cls, context):
        print("DEBUG: create_default_two_point_vps CALLED")
        ts = context.scene.perspective_tool_settings_splines
        prefix = VP_TYPE_SPECIFIC_PREFIX_MAP['TWO_POINT']
        
        horizon_z_level = ts.horizon_y_level 
        horizon_ctrl = get_horizon_control_object()
        if not horizon_ctrl:
            print("DEBUG create_default_two_point_vps: No horizon control, generating one.")
            bpy.ops.perspective_splines.generate_horizon('EXEC_DEFAULT')
            horizon_ctrl = get_horizon_control_object() # Attempt to get it again
        
        if horizon_ctrl: # If it exists (or was just created)
            horizon_z_level = horizon_ctrl.location.z
            if abs(ts.horizon_y_level - horizon_z_level) > 0.001:
                ts.horizon_y_level = horizon_z_level # Sync property to actual control Z
                print(f"DEBUG create_default_two_point_vps: Synced ts.horizon_y_level to Horizon Control Z: {horizon_z_level}")
        else:
             print("DEBUG create_default_two_point_vps: Failed to ensure horizon control, using ts.horizon_y_level for new VPs.")


        print(f"DEBUG create_default_two_point_vps: Target horizon Z for VPs: {horizon_z_level}")

        vp_definitions = [
            {"name_suffix": "_1", "default_x_offset": -10.0, "color_prop": ts.two_point_vp1_empty_color},
            {"name_suffix": "_2", "default_x_offset": 10.0,  "color_prop": ts.two_point_vp2_empty_color}
        ]
        
        for vp_def in vp_definitions:
            vp_name = prefix + vp_def["name_suffix"]
            vp_color = vp_def["color_prop"]
            existing_vp = bpy.data.objects.get(vp_name)

            if existing_vp:
                print(f"DEBUG create_default_two_point_vps: VP '{vp_name}' exists. Ensuring Z is on horizon {horizon_z_level}.")
                current_loc = existing_vp.location.copy()
                if abs(current_loc.z - horizon_z_level) > 0.001 :
                    current_loc.z = horizon_z_level
                    existing_vp.location = current_loc # Snap Z to horizon
                add_vp_empty_if_missing(context, vp_name, current_loc, vp_color) 
            else: 
                initial_loc = Vector((vp_def["default_x_offset"], 0.0, horizon_z_level))
                print(f"DEBUG create_default_two_point_vps: Creating NEW VP: '{vp_name}' at {initial_loc}")
                add_vp_empty_if_missing(context, vp_name, initial_loc, vp_color)


class PERSPECTIVE_OT_generate_2p_vp1_lines(Operator):
    bl_idname = "perspective_splines.generate_2p_vp1_lines"
    bl_label = "Generate 2P VP1 Lines"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        bpy.ops.perspective_splines.create_2p_vps_if_needed()

        vps = get_vanishing_points('TWO_POINT')
        if not vps:
            self.report({'ERROR'}, "2P VP1 not found. Create VPs first."); return {'CANCELLED'}
        vp1 = vps[0] # Assumes sorted, VP_2P_1

        guides_coll = get_guides_collection(context)
        clear_guides_with_prefix(context, ["2P_Guides_VP1_"]) # Note the underscore
        ext = ts.two_point_line_extension
        
        lines_data = generate_radial_lines_in_plane(vp1.location.copy(), ts.two_point_grid_density_vp1, ext, 'XZ')
        if not lines_data:
            self.report({'INFO'}, "No VP1 lines to generate."); return {'FINISHED'}
        
        opac = ts.guide_curves_opacity
        thickness = ts.guide_curves_thickness
        created_count = 0
        for i, pts_list in enumerate(lines_data):
            if create_curve_object(context, f"2P_Guides_VP1_{i+1}", [pts_list], guides_coll, thickness, opac):
                created_count += 1
        self.report({'INFO'}, f"Generated {created_count} 2P VP1 lines.")
        update_dynamic_horizon_line_curve(context)
        return {'FINISHED'}

class PERSPECTIVE_OT_generate_2p_vp2_lines(Operator):
    bl_idname = "perspective_splines.generate_2p_vp2_lines"
    bl_label = "Generate 2P VP2 Lines"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        bpy.ops.perspective_splines.create_2p_vps_if_needed()

        vps = get_vanishing_points('TWO_POINT')
        if len(vps) < 2:
            self.report({'ERROR'}, "2P VP2 not found. Create VPs first."); return {'CANCELLED'}
        vp2 = vps[1] # Assumes sorted, VP_2P_2

        guides_coll = get_guides_collection(context)
        clear_guides_with_prefix(context, ["2P_Guides_VP2_"]) # Note the underscore
        ext = ts.two_point_line_extension
        
        lines_data = generate_radial_lines_in_plane(vp2.location.copy(), ts.two_point_grid_density_vp2, ext, 'XZ')
        if not lines_data:
            self.report({'INFO'}, "No VP2 lines to generate."); return {'FINISHED'}

        opac = ts.guide_curves_opacity
        thickness = ts.guide_curves_thickness
        created_count = 0
        for i, pts_list in enumerate(lines_data):
            if create_curve_object(context, f"2P_Guides_VP2_{i+1}", [pts_list], guides_coll, thickness, opac):
                created_count +=1
        self.report({'INFO'}, f"Generated {created_count} 2P VP2 lines.")
        update_dynamic_horizon_line_curve(context)
        return {'FINISHED'}

class PERSPECTIVE_OT_generate_2p_vertical_lines(Operator):
    bl_idname = "perspective_splines.generate_2p_vertical_lines"
    bl_label = "Generate 2P Vertical Lines"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        bpy.ops.perspective_splines.create_2p_vps_if_needed() # Ensure VPs exist for context

        vps = get_vanishing_points('TWO_POINT')
        if len(vps) < 2:
            self.report({'ERROR'}, "2P VPs not found for vertical line generation."); return {'CANCELLED'}
        vp1_loc, vp2_loc = vps[0].location.copy(), vps[1].location.copy()

        guides_coll = get_guides_collection(context)
        clear_guides_with_prefix(context, ["2P_Guides_Vertical_"]) # Note the underscore
        
        verts_data = []
        num_verts = ts.two_point_grid_density_vertical
        if num_verts >= 0:
            h = ts.two_point_grid_height
            y_off = ts.two_point_grid_depth_offset
            x_space = ts.two_point_verticals_x_spacing_factor
            avg_vp_x = (vp1_loc.x + vp2_loc.x) / 2.0
            avg_vp_y = (vp1_loc.y + vp2_loc.y) / 2.0 
            horizon_z = vp1_loc.z 
            vp_x_dist = abs(vp1_loc.x - vp2_loc.x)
            ext_fallback = ts.two_point_line_extension # Use this if VPs are too close
            spread_width = vp_x_dist * x_space if vp_x_dist > 0.1 else ext_fallback * 0.5 * x_space
            start_x = avg_vp_x - spread_width / 2.0
            plane_y = avg_vp_y + y_off
            
            for i in range(num_verts + 1): 
                t = (i / num_verts) if num_verts > 0 else 0.5 
                curr_x = start_x + t * spread_width
                verts_data.append([Vector((curr_x, plane_y, horizon_z - h/2.0)), 
                                   Vector((curr_x, plane_y, horizon_z + h/2.0))])
        
        if not verts_data:
            self.report({'INFO'}, "No Vertical lines to generate."); return {'FINISHED'}

        opac = ts.guide_curves_opacity
        thickness = ts.guide_curves_thickness
        created_count = 0
        for i, pts_list in enumerate(verts_data):
            create_curve_object(context, f"2P_Guides_Vertical_{i+1}", [pts_list], guides_coll, thickness, opac)
            created_count += 1
        self.report({'INFO'}, f"Generated {created_count} 2P Vertical lines.")
        update_dynamic_horizon_line_curve(context)
        return {'FINISHED'}

    
# (Around line 1050, after generate_two_point and before generate_fish_eye)

class PERSPECTIVE_OT_create_3p_vps_if_needed(Operator):
    """Helper to ensure 3P VPs exist, called by specific 3P line generators."""
    bl_idname = "perspective_splines.create_3p_vps_if_needed"
    bl_label = "Ensure 3P VPs"
    bl_options = {'REGISTER', 'INTERNAL'} # Internal, not for UI

    @classmethod
    def create_default_three_point_vps(cls, context):
        print("DEBUG: create_default_three_point_vps CALLED")
        ts = context.scene.perspective_tool_settings_splines
        h_pref = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_H']
        v_pref = VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_V']

        horizon_z_level = ts.horizon_y_level
        horizon_ctrl = get_horizon_control_object()
        if not horizon_ctrl:
            print("DEBUG create_default_three_point_vps: No horizon control, generating one.")
            bpy.ops.perspective_splines.generate_horizon('EXEC_DEFAULT')
            horizon_ctrl = get_horizon_control_object()
        
        if horizon_ctrl:
            horizon_z_level = horizon_ctrl.location.z
            if abs(ts.horizon_y_level - horizon_z_level) > 0.001:
                ts.horizon_y_level = horizon_z_level
                print(f"DEBUG create_default_three_point_vps: Synced ts.horizon_y_level to Horizon Control Z: {horizon_z_level}")
        else:
            print("DEBUG create_default_three_point_vps: Failed to ensure horizon control.")

        print(f"DEBUG create_default_three_point_vps: Target horizon Z for H_VPs: {horizon_z_level}")

        vp_h1_name = h_pref + "_1"
        vp_h2_name = h_pref + "_2"
        vp_v_name = v_pref + "_1"

        vp_definitions = [
            {"name": vp_h1_name, "default_offset": Vector((-10.0, 0.0, 0.0)), "color_prop": ts.three_point_vp_h1_empty_color, "is_horizontal": True},
            {"name": vp_h2_name, "default_offset": Vector((10.0, 0.0, 0.0)),  "color_prop": ts.three_point_vp_h2_empty_color, "is_horizontal": True},
            {"name": vp_v_name,  "default_offset": Vector((0.0, 0.0, -10.0)), "color_prop": ts.three_point_vp_v_empty_color, "is_horizontal": False}
        ]
        
        for vp_def in vp_definitions:
            vp_name = vp_def["name"]
            vp_color = vp_def["color_prop"]
            is_horizontal_vp = vp_def["is_horizontal"]
            existing_vp = bpy.data.objects.get(vp_name)

            current_loc_for_vp = Vector(vp_def["default_offset"]) # Start with offset
            if is_horizontal_vp:
                current_loc_for_vp.z = horizon_z_level # Set Z to horizon
            else: # Vertical VP
                # Center X between H VPs if they exist, add Z offset to horizon
                h_vp1 = bpy.data.objects.get(vp_h1_name)
                h_vp2 = bpy.data.objects.get(vp_h2_name)
                avg_h_x = 0.0
                if h_vp1 and h_vp2: avg_h_x = (h_vp1.location.x + h_vp2.location.x) / 2.0
                elif h_vp1: avg_h_x = h_vp1.location.x
                elif h_vp2: avg_h_x = h_vp2.location.x
                current_loc_for_vp.x += avg_h_x # Add offset to average (or 0 if no H_VPs)
                current_loc_for_vp.z += horizon_z_level # Z offset is relative to horizon


            if existing_vp:
                print(f"DEBUG create_default_three_point_vps: VP '{vp_name}' exists. Ensuring location & color.")
                target_loc = existing_vp.location.copy()
                if is_horizontal_vp: # Snap existing horizontal VPs to horizon
                    if abs(target_loc.z - horizon_z_level) > 0.001:
                        target_loc.z = horizon_z_level
                # For vertical VP, if it exists, we largely preserve its full location.
                # The default_offset logic above is more for initial creation.
                # However, one might argue its X should also align with H_VPs if H_VPs moved. This is a design choice.
                # For now, if V_VP exists, its manually set position is respected.
                add_vp_empty_if_missing(context, vp_name, target_loc, vp_color)
            else:
                print(f"DEBUG create_default_three_point_vps: Creating NEW VP: '{vp_name}' at {current_loc_for_vp}")
                add_vp_empty_if_missing(context, vp_name, current_loc_for_vp, vp_color)


    def execute(self, context):
        PERSPECTIVE_OT_create_3p_vps_if_needed.create_default_three_point_vps(context)
        return {'FINISHED'}


class PERSPECTIVE_OT_generate_3p_h1_lines(Operator):
    bl_idname = "perspective_splines.generate_3p_h1_lines"
    bl_label = "Generate 3P H-VP1 Lines"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        bpy.ops.perspective_splines.create_3p_vps_if_needed() # Ensure VPs exist

        vps_h = get_vanishing_points('THREE_POINT_H')
        if not vps_h:
            self.report({'ERROR'}, "3P H-VP1 not found. Create VPs first."); return {'CANCELLED'}
        vp_h1 = vps_h[0] # Assumes sorted, VP_3P_H_1

        guides_coll = get_guides_collection(context)
        clear_guides_with_prefix(context, ["3P_Guides_H1"]) # Clear only H1 lines
        ext = ts.three_point_line_extension
        
        lines_data = generate_radial_lines_in_plane(vp_h1.location.copy(), ts.three_point_vp_h1_density, ext, 'XZ')
        if not lines_data:
            self.report({'INFO'}, "No H1 lines to generate."); return {'FINISHED'}
        
        opac = ts.guide_curves_opacity
        created_count = 0
        for i, pts_list in enumerate(lines_data):
            if create_curve_object(context, f"3P_Guides_H1_{i+1}", [pts_list], guides_coll, ts.guide_curves_thickness, opac):
                created_count += 1
        self.report({'INFO'}, f"Generated {created_count} 3P H-VP1 lines.")
        update_dynamic_horizon_line_curve(context)
        return {'FINISHED'}

class PERSPECTIVE_OT_generate_3p_h2_lines(bpy.types.Operator):
    """Generate guide curves for the second horizontal VP in Three-Point Perspective."""
    bl_idname = "perspective_splines.generate_3p_h2_lines"
    bl_label = "Generate 3P H-VP2 Lines"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        bpy.ops.perspective_splines.create_3p_vps_if_needed()  # Ensure all 3P VPs exist

        vps_h = get_vanishing_points('THREE_POINT_H')
        if len(vps_h) < 2:
            self.report({'ERROR'}, "3P H-VP2 not found. Create VPs first.")
            return {'CANCELLED'}
        vp_h2 = vps_h[1]  # Expecting VP_3P_H_2 to be the second horizontal VP.
        print("DEBUG VP2: VP_3P_H_2 location:", vp_h2.location)

        guides_coll = get_guides_collection(context)
        clear_guides_with_prefix(context, ["3P_Guides_H2"])
        ext = ts.three_point_line_extension

        lines_data = generate_radial_lines_in_plane(vp_h2.location.copy(), ts.three_point_vp_h2_density, ext, 'XZ')
        print("DEBUG VP2: Generated lines_data =", lines_data)
        if not lines_data:
            self.report({'INFO'}, "No H2 lines to generate.")
            return {'FINISHED'}

        opac = ts.guide_curves_opacity
        created_count = 0
        for i, pts_list in enumerate(lines_data):
            # For debugging, check if forcing a color makes it visible.
            new_curve = create_curve_object(context, f"3P_Guides_H2_{i+1}", [pts_list], guides_coll,
                                             ts.guide_curves_thickness, opac, color_rgb=(1.0, 0.0, 0.0))
            if new_curve:
                print(f"DEBUG VP2: Created guide curve {new_curve.name}")
                created_count += 1
            else:
                print(f"DEBUG VP2: Failed to create guide curve for index {i+1}")
        self.report({'INFO'}, f"Generated {created_count} 3P H-VP2 lines.")
        context.area.tag_redraw()
        return {'FINISHED'}



class PERSPECTIVE_OT_generate_3p_v_lines(Operator):
    bl_idname = "perspective_splines.generate_3p_v_lines"
    bl_label = "Generate 3P V-VP Lines"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        bpy.ops.perspective_splines.create_3p_vps_if_needed()

        vps_v = get_vanishing_points('THREE_POINT_V')
        if not vps_v:
            self.report({'ERROR'}, "3P V-VP not found. Create VPs first."); return {'CANCELLED'}
        vp_v1 = vps_v[0]

        guides_coll = get_guides_collection(context)
        clear_guides_with_prefix(context, ["3P_Guides_V"])
        ext = ts.three_point_line_extension

        lines_data = generate_radial_lines_in_plane(vp_v1.location.copy(), ts.three_point_vp_v_density, ext, 'XZ')
        if not lines_data:
            self.report({'INFO'}, "No V lines to generate."); return {'FINISHED'}

        opac = ts.guide_curves_opacity
        created_count = 0
        for i, pts_list in enumerate(lines_data):
            if create_curve_object(context, f"3P_Guides_V_{i+1}", [pts_list], guides_coll, ts.guide_curves_thickness, opac):
                created_count +=1
        self.report({'INFO'}, f"Generated {created_count} 3P V-VP lines.")
        update_dynamic_horizon_line_curve(context) # V-VP doesn't define horizon, but good to update
        return {'FINISHED'}    


# (This class is after the 3P line generation operators and before align_camera)

class PERSPECTIVE_OT_generate_fish_eye_splines(Operator):
    bl_idname = "perspective_splines.generate_fish_eye"
    bl_label = "Generate FE Lines"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def create_default_fish_eye_center(cls, context):
        print("DEBUG FishEye: create_default_fish_eye_center CALLED")
        ts = context.scene.perspective_tool_settings_splines
        helpers_coll = get_helpers_collection(context) # Ensure helpers collection exists

        fe_vp_name = VP_TYPE_SPECIFIC_PREFIX_MAP['FISH_EYE'] + "_1" # e.g., VP_FE_Center_1
        
        # Determine color for the VP empty
        vp_color = (0.5, 0.2, 0.8, 1.0) # Default if property doesn't exist
        if hasattr(ts, 'fish_eye_vp_empty_color'):
            vp_color = list(ts.fish_eye_vp_empty_color)
        
        existing_vp = bpy.data.objects.get(fe_vp_name)
        
        if existing_vp:
            print(f"DEBUG FishEye: VP {fe_vp_name} exists. Preserving location: {existing_vp.location}")
            # Ensure it's in the correct collection
            if existing_vp.name not in helpers_coll.objects:
                for coll in existing_vp.users_collection:
                    if coll != helpers_coll:
                        coll.objects.unlink(existing_vp)
                helpers_coll.objects.link(existing_vp)
            
            # Update color if different from setting
            current_color_tuple = tuple(round(c, 4) for c in existing_vp.color)
            setting_color_tuple = tuple(round(c, 4) for c in vp_color)
            if current_color_tuple != setting_color_tuple:
                print(f"DEBUG FishEye: Updating color for existing VP {existing_vp.name}")
                existing_vp.color = vp_color # Already a list or tuple
                update_vp_empty_colors(ts, context) # Call master color update
        else:
            # VP does not exist, create it at world origin (user can move it)
            default_loc = Vector((0.0, 0.0, 0.0))
            print(f"DEBUG FishEye: Creating NEW VP: {fe_vp_name} at {default_loc}")
            new_vp = add_vp_empty_if_missing(context, fe_vp_name, default_loc, vp_color)
            if new_vp:
                update_vp_empty_colors(ts, context) # Call master color update
            else:
                print(f"DEBUG FishEye: FAILED to create VP {fe_vp_name}")
        
        # FishEye typically doesn't have a horizon line in the same way,
        # but call update_dynamic_horizon_line_curve anyway in case it has a default behavior for 'NONE'
        # or if other types of horizon logic might apply. It will hide if no points are set.
        update_dynamic_horizon_line_curve(context)


    def execute(self, context):
        print("DEBUG FishEye: Execute operator CALLED")
        ts = context.scene.perspective_tool_settings_splines
        
        # Ensure the center VP exists or is created
        PERSPECTIVE_OT_generate_fish_eye_splines.create_default_fish_eye_center(context)
        
        fe_centers = get_vanishing_points('FISH_EYE') 
        if not fe_centers: 
            print("DEBUG FishEye Execute: FE Center VP NOT found after attempting creation.")
            self.report({'ERROR'}, "FE Center VP not found. Cannot generate lines."); return {'CANCELLED'}
        
        fe_center_obj = fe_centers[0] # Should be VP_FE_Center_1
        print(f"DEBUG FishEye Execute: Using FE Center VP: {fe_center_obj.name} at {fe_center_obj.location}")
        
        guides_coll = get_guides_collection(context)
        clear_guides_with_prefix(context, ["FE_Guides_"]) # Clear only FE guides (added underscore)
        
        center_loc = fe_center_obj.location.copy() # Use the current location of the VP
        n_lon, n_lat = ts.fish_eye_grid_radial, ts.fish_eye_grid_concentric
        segs, radius, h_scale = ts.fish_eye_segments_per_curve, ts.fish_eye_grid_radius, ts.fish_eye_horizontal_scale
        curves_data_to_create = [] 

        print(f"DEBUG FishEye Execute: n_lon={n_lon}, n_lat={n_lat}, draw_latitude={ts.fish_eye_draw_latitude}, radius={radius}")

        if n_lon > 0 and segs > 1: 
            print(f"DEBUG FishEye Execute: Generating {n_lon} longitude lines...")
            for i in range(n_lon):
                phi = (2 * math.pi * i) / n_lon 
                pts_longitude = []
                for j in range(segs + 1): 
                    theta = math.pi * j / segs 
                    x = radius * math.sin(theta) * math.cos(phi) * h_scale
                    y = radius * math.sin(theta) * math.sin(phi) 
                    z = radius * math.cos(theta)
                    # Add to the VP's current location
                    pts_longitude.append(center_loc + Vector((x,y,z))) 
                curves_data_to_create.append({'points_list': [pts_longitude], 'is_cyclic': False, 'name_suffix': f"Lon_{i}"})
        
        if ts.fish_eye_draw_latitude and n_lat > 0 and segs > 1: 
            print(f"DEBUG FishEye Execute: Generating {n_lat} latitude lines...")
            for i in range(1, n_lat + 1): 
                theta = math.pi * i / (n_lat + 1) 
                ring_radius_at_z = radius * math.sin(theta)
                z_offset_from_center = radius * math.cos(theta)
                pts_latitude = []
                for j in range(segs + 1): 
                    phi = (2 * math.pi * j) / segs 
                    x = ring_radius_at_z * math.cos(phi) * h_scale
                    y = ring_radius_at_z * math.sin(phi)
                    z_coord = z_offset_from_center # This is relative to the sphere's own center
                    # Add to the VP's current location
                    pts_latitude.append(center_loc + Vector((x,y,z_coord)))
                curves_data_to_create.append({'points_list': [pts_latitude], 'is_cyclic': True, 'name_suffix': f"Lat_{i}"})
        
        if not curves_data_to_create: 
            print("DEBUG FishEye Execute: No curve data was generated for FE lines.")
            self.report({'INFO'}, "No Fish Eye lines to generate based on current settings."); return {'FINISHED'}
        
        print(f"DEBUG FishEye Execute: Attempting to create {len(curves_data_to_create)} FE curve objects.")
        opac = ts.guide_curves_opacity 
        thickness = ts.guide_curves_thickness
        created_count = 0
        for i, curve_def in enumerate(curves_data_to_create):
            obj_name = f"FE_Guides_{curve_def['name_suffix']}"
            # create_curve_object uses random colors by default if color_rgb is not passed
            if create_curve_object(context, obj_name, curve_def['points_list'], guides_coll,
                                thickness, opac, is_cyclic=curve_def['is_cyclic'], curve_type='BEZIER'):
                created_count +=1
        
        self.report({'INFO'}, f"Generated {created_count} Fish Eye line objects.")
        return {'FINISHED'}

class PERSPECTIVE_OT_align_camera_splines(Operator):
    bl_idname = "perspective_splines.align_camera"
    bl_label = "Align Camera to Perspective"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context): return context.scene.camera is not None
    def execute(self, context):
        ts = context.scene.perspective_tool_settings_splines
        cam = context.scene.camera
        if not cam: # Should be caught by poll, but defensive
            self.report({'ERROR'}, "No active camera in scene.")
            return {'CANCELLED'}

        target_point = Vector((0,0,0)) # Point camera looks at
        cam_height_origin_z = 0.0 # Z level from which eye height is measured

        curr_type = ts.current_perspective_type
        horizon_ctrl = get_horizon_control_object()

        if curr_type == 'ONE_POINT':
            vps = get_vanishing_points('ONE_POINT')
            if vps: 
                target_point = vps[0].location.copy()
                cam_height_origin_z = vps[0].location.z
            elif horizon_ctrl: 
                cam_height_origin_z = horizon_ctrl.location.z
                target_point = Vector((0, 0, cam_height_origin_z)) # Target center of horizon
            else: # Fallback to tool setting
                cam_height_origin_z = ts.horizon_y_level
                target_point = Vector((0, 0, cam_height_origin_z))

        elif curr_type == 'TWO_POINT':
            vps = get_vanishing_points('TWO_POINT')
            if len(vps) >=2: 
                target_point = (vps[0].location + vps[1].location) / 2.0
                cam_height_origin_z = vps[0].location.z # VPs are on horizon
            elif horizon_ctrl:
                cam_height_origin_z = horizon_ctrl.location.z
                target_point = Vector((0, 0, cam_height_origin_z))
            else:
                cam_height_origin_z = ts.horizon_y_level
                target_point = Vector((0, 0, cam_height_origin_z))
        
        elif curr_type == 'THREE_POINT':
            vps_h = get_vanishing_points('THREE_POINT_H')
            # For 3P, typically target the center of the H_VPs on the horizon
            if len(vps_h) >=2: 
                target_point = (vps_h[0].location + vps_h[1].location) / 2.0
                cam_height_origin_z = vps_h[0].location.z
                # Optional: Could consider V_VP for target_point.z if desired for worm's/bird's eye view aiming
                # vps_v = get_vanishing_points('THREE_POINT_V')
                # if vps_v: target_point.z = vps_v[0].location.z 
            elif horizon_ctrl:
                cam_height_origin_z = horizon_ctrl.location.z
                target_point = Vector((0, 0, cam_height_origin_z))
            else:
                cam_height_origin_z = ts.horizon_y_level
                target_point = Vector((0, 0, cam_height_origin_z))

        elif curr_type == 'FISH_EYE':
            vps = get_vanishing_points('FISH_EYE')
            if vps: 
                target_point = vps[0].location.copy()
                cam_height_origin_z = vps[0].location.z # Camera level relative to FE center Z
            else: # Fallback to world origin if no FE center
                target_point = Vector((0,0,0))
                cam_height_origin_z = 0.0
        
        else: # 'NONE' or unhandled type
            if horizon_ctrl: 
                cam_height_origin_z = horizon_ctrl.location.z
                target_point = Vector((0, 0, cam_height_origin_z))
            else: 
                cam_height_origin_z = ts.horizon_y_level
                target_point = Vector((0, 0, cam_height_origin_z))
            self.report({'INFO'}, f"Aligning camera to default target at Z={cam_height_origin_z:.2f}.")

        # Position camera: typically behind target_point along Y, at eye height
        # Assuming standard Blender coordinate system where -Y is "into the screen" from front view
        cam.location = target_point + Vector((0, -ts.camera_distance, 0)) # Move back along Y
        cam.location.z = cam_height_origin_z + ts.camera_eye_height       # Set Z based on origin + eye height

        # Point camera towards target_point
        direction_to_target = target_point - cam.location
        if direction_to_target.length > 0.0001: # Avoid issues with zero-length vector
            # Using 'track_to_object_tuple' logic: (target_object, track_axis, up_axis)
            # We want camera's -Z axis to point towards target, Y axis as up.
            cam.rotation_euler = direction_to_target.to_track_quat('-Z', 'Y').to_euler('XYZ')
        
        self.report({'INFO'}, f"Camera aligned for {curr_type if curr_type != 'NONE' else 'default view'}.")
        return {'FINISHED'}

# This operator is now redundant if PERSPECTIVE_OT_merge_and_convert_to_gpencil is used from the UI.
# It's commented out in classes_splines. If you want to keep it for other purposes, ensure its context override is also robust.
# (This operator should be around line 1067 or after PERSPECTIVE_OT_align_camera_splines)
# Replace the existing PERSPECTIVE_OT_convert_to_grease_pencil with this:

# -----------------------------------------------------------
# UI Panel
# -----------------------------------------------------------
# -----------------------------------------------------------
# UI Panel
# -----------------------------------------------------------
# (This class is usually defined after all your operators and before the registration section)

class VIEW3D_PT_rogue_perspective_grids(Panel):
    bl_label = "Construction Grids"
    bl_idname = "VIEW3D_PT_rogue_perspective_grids"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'RogueAI' # Same tab as main panel
    bl_parent_id = "VIEW3D_PT_rogue_perspective_ai" # Make it a subpanel
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        ts = context.scene.perspective_tool_settings_splines

        box = layout.box()
        box.label(text="Box Grid Parameters:")
        col = box.column(align=True)
        col.prop(ts, "grid_center", text="Center")
        col.prop(ts, "grid_size", text="Size")
        row = col.row(align=True)
        row.prop(ts, "grid_subdivisions_u", text="Subs U")
        row.prop(ts, "grid_subdivisions_v", text="Subs V")

        box.separator()
        box.label(text="Draw Planes:")
        col_planes = box.column(align=True)
        row1 = col_planes.row(align=True)
        row1.prop(ts, "grid_draw_front", text="Front", toggle=True)
        row1.prop(ts, "grid_draw_back", text="Back", toggle=True)
        row2 = col_planes.row(align=True)
        row2.prop(ts, "grid_draw_top", text="Top", toggle=True)
        row2.prop(ts, "grid_draw_bottom", text="Bottom", toggle=True)
        row3 = col_planes.row(align=True)
        row3.prop(ts, "grid_draw_left", text="Left", toggle=True)
        row3.prop(ts, "grid_draw_right", text="Right", toggle=True)
        
        layout.separator()
        layout.operator("perspective_splines.create_box_grid", text="Create/Update Box Grid", icon='MESH_GRID')
        
        # Corrected Clear Grid Planes button
        layout.operator("perspective_splines.clear_grid_planes", text="Clear Grid Planes", icon='X')
        
        layout.separator() 
        
        # Added Toggle Grid Visibility button
        toggle_op = layout.operator(
            PERSPECTIVE_OT_toggle_guide_visibility.bl_idname,
            text="Toggle Grid Visibility",
            icon='HIDE_OFF' # Initial icon, can be made dynamic if state is tracked
        )
        toggle_op.group_prefix = "GridPlane_"






class VIEW3D_PT_rogue_perspective_trimmer(bpy.types.Panel):
    bl_label = "Guide Clipper"
    bl_idname = "VIEW3D_PT_rogue_perspective_trimmer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'RogueAI'
    bl_parent_id = "VIEW3D_PT_rogue_perspective_ai"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        ts = getattr(context.scene, "perspective_tool_settings_splines", None)
        if not ts:
            layout.label(text="Perspective settings not found.")
            return

        main_box = layout.box()
        col_main = main_box.column(align=True)

        col_main.label(text="Clip Guides to Camera Borders:")
        col_main.operator(
            "perspective_splines.clip_guides_to_camera",
            text="Clip Now",
            icon='MOD_LENGTH'
        )


    
# -----------------------------------------------------------
# UI Panel for Perspective Extraction
# -----------------------------------------------------------
class VIEW3D_PT_perspective_extraction(bpy.types.Panel):
    bl_label = "Perspective Extraction Helper"
    bl_idname = "VIEW3D_PT_perspective_extraction"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'RogueAI'
    bl_parent_id = "VIEW3D_PT_rogue_perspective_ai"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (hasattr(context.scene, "perspective_tool_settings_splines") and
                context.scene.perspective_tool_settings_splines is not None)

    def draw(self, context):
        layout = self.layout
        ts = context.scene.perspective_tool_settings_splines
        if not ts:
            layout.label(text="Perspective settings not found.", icon='ERROR')
            return

        # --- Visual Aid Controls ---
        aid_box = layout.box()
        aid_box.label(text="Visual Aid Controls:")
        aid_row = aid_box.row(align=True)
        aid_row.prop(ts, "show_extraction_helper_lines", text="Show Aid Lines", toggle=True)
        aid_row.enabled = ts.current_perspective_type in ['ONE_POINT', 'TWO_POINT', 'THREE_POINT']
        refresh_op = aid_row.operator("perspective_splines.refresh_extraction_aids", text="", icon='FILE_REFRESH')
        if hasattr(refresh_op, 'from_selection_change'):
            refresh_op.from_selection_change = True

        helper_ops_row = aid_box.row(align=True)
        helper_ops_row.operator("perspective_splines.toggle_all_helpers", text="Toggle Helpers View", icon='HIDE_OFF')
        helper_ops_row.operator("perspective_splines.delete_all_helpers", text="Delete All Helpers", icon='TRASH')
        select_all_op = aid_box.operator("perspective_splines.select_helper_empties", text="Select ALL Aid Empties", icon='RESTRICT_SELECT_OFF')
        select_all_op.helper_set_identifier = "ALL_AIDS"

        if not aid_row.enabled and ts.show_extraction_helper_lines:
            aid_box.label(text="Aid lines active for 1P/2P/3P modes.", icon='INFO')

        layout.separator()

        # --- Extraction UI Based on Perspective Mode ---
        if ts.current_perspective_type == 'ONE_POINT':
            # [Your ONE_POINT UI code...]
            box = layout.box()
            col = box.column(align=True)
            col.label(text="1-Point VP (from 4 Empties):", icon='EMPTY_DATA')
            row = col.row(align=True)
            row.operator("perspective_splines.add_1p_extraction_empties", text="Add 1P Helpers", icon='ADD')
            op = row.operator("perspective_splines.select_helper_empties", text="Select 1P Helpers", icon='RESTRICT_SELECT_OFF')
            op.helper_set_identifier = "1P_Aid"
            col.separator()
            instr = col.column(align=True)
            instr.label(text="Instructions:")
            instr.label(text=" 1. Add helpers and position the 4 '1P_Aid' empties.")
            instr.label(text=" 2. Select them (or use 'Select 1P Helpers').")
            instr.label(text=" 3. Click 'Set 1P VP from Selection'.")
            col.separator()
            col.operator("perspective_splines.extract_1p_from_empties", text="Set 1P VP from Selection", icon='TRACKING_FORWARDS')

            sel = [o for o in context.selected_objects if o.type == 'EMPTY' and "1P_Aid" in o.name]
            if len(sel) == 4:
                col.label(text="Status: 4 '1P_Aid' Empties selected. Ready.", icon='CHECKMARK')
            else:
                col.label(text=f"Status: Select 4 '1P_Aid' Empties (found {len(sel)}).", icon='ERROR')

        elif ts.current_perspective_type == 'TWO_POINT':
            # [Your TWO_POINT UI code...]
            box = layout.box()
            col = box.column(align=True)
            col.label(text="2-Point VPs (from 4 Empties each):", icon='EMPTY_AXIS')
            col.separator()
            col_vp1 = col.column(align=True)
            col_vp1.label(text="Vanishing Point 1 (VP1):")
            row = col_vp1.row(align=True)
            row.operator("perspective_splines.add_2p_vp1_helpers", text="Add VP1 Helpers", icon='ADD')
            op = row.operator("perspective_splines.select_helper_empties", text="Select VP1 Helpers", icon='RESTRICT_SELECT_OFF')
            op.helper_set_identifier = "2P_VP1_Aid"
            col_vp1.operator("perspective_splines.extract_2p_vp1_from_empties", text="Set VP1 from Selection", icon='TRACKING_FORWARDS')
            col.separator()
            col_vp2 = col.column(align=True)
            col_vp2.label(text="Vanishing Point 2 (VP2):")
            row = col_vp2.row(align=True)
            row.operator("perspective_splines.add_2p_vp2_helpers", text="Add VP2 Helpers", icon='ADD')
            op = row.operator("perspective_splines.select_helper_empties", text="Select VP2 Helpers", icon='RESTRICT_SELECT_OFF')
            op.helper_set_identifier = "2P_VP2_Aid"
            col_vp2.operator("perspective_splines.extract_2p_vp2_from_empties", text="Set VP2 from Selection", icon='TRACKING_FORWARDS')
            col.separator()
            col.label(text="Instructions: For each VP, add helpers, position them, select helpers, then set VP.", icon='INFO')

        elif ts.current_perspective_type == 'THREE_POINT':
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Three-Point VP Extraction:")

            # Horizontal VP1 section
            col_h1 = col.column(align=True)
            col_h1.label(text="Horizontal VP1 (H_VP1):")
            row = col_h1.row(align=True)
            row.operator("perspective_splines.add_3p_h_vp1_helpers", text="Add H1 Helpers", icon='ADD')
            op = row.operator("perspective_splines.select_helper_empties", text="Select H1 Helpers", icon='RESTRICT_SELECT_OFF')
            op.helper_set_identifier = "3P_H1_Aid"
            col_h1.operator("perspective_splines.extract_3p_h_vp1_from_empties", text="Set H_VP1 from Selection", icon='TRACKING_FORWARDS')

            # Horizontal VP2 section
            col.separator()
            col_h2 = col.column(align=True)
            col_h2.label(text="Horizontal VP2 (H_VP2):")
            row = col_h2.row(align=True)
            row.operator("perspective_splines.add_3p_h_vp2_helpers", text="Add H2 Helpers", icon='ADD')
            op = row.operator("perspective_splines.select_helper_empties", text="Select H2 Helpers", icon='RESTRICT_SELECT_OFF')
            op.helper_set_identifier = "3P_H2_Aid"
            col_h2.operator("perspective_splines.extract_3p_h_vp2_from_empties", text="Set H_VP2 from Selection", icon='TRACKING_FORWARDS')

            # Vertical VP section
            col.separator()
            col_v = col.column(align=True)
            col_v.label(text="Vertical VP (V_VP):")
            row = col_v.row(align=True)
            row.operator("perspective_splines.add_3p_v_vp_helpers", text="Add V Helpers", icon='ADD')
            op = row.operator("perspective_splines.select_helper_empties", text="Select V Helpers", icon='RESTRICT_SELECT_OFF')
            op.helper_set_identifier = "3P_V_Aid"
            col_v.operator("perspective_splines.extract_3p_v_from_empties", text="Set V_VP from Selection", icon='TRACKING_FORWARDS')



        else:
            layout.label(text=f"No Empty-based extraction for '{ts.current_perspective_type}' mode.", icon='INFO')

        layout.separator()

        # --- Camera Alignment ---
        #cam_box = layout.box()
        #cam_col = cam_box.column()
        #cam_col.label(text="Camera Alignment:")
        #cam_col.prop(ts, "camera_eye_height")
        #cam_col.prop(ts, "camera_distance")
        #cam_col.operator("perspective_splines.align_camera", icon='CAMERA_DATA')
        #layout.separator()

        # --- Master Clear Button ---
        #layout.operator("perspective_splines.clear_all", text="Clear ALL Perspective Data", icon='TRASH')

        # Here we call the global finalize function to include the finalize UI
        #draw_finalize_guides_section(layout, context)




class Rogue_Perspective_AI_PT_main(Panel):
    bl_label = "Rogue Perspective AI"
    bl_idname = "VIEW3D_PT_rogue_perspective_ai"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'RogueAI' # This is the Tab name in the N-Panel

    @classmethod
    def poll(cls, context):
        # Ensure the settings property group is available on the scene
        return hasattr(context.scene, "perspective_tool_settings_splines") and \
               context.scene.perspective_tool_settings_splines is not None

    # --- Helper method for the Finalize Guides section ---
    # Correctly indented as a method of this class
    def draw_finalize_guides_section(self, layout, context):
        tool_settings = context.scene.perspective_tool_settings_splines
        current_perspective_type = tool_settings.current_perspective_type

        finalize_box = layout.box()
        finalize_box.label(text="Finalize & Manage Guides:") # Slightly clearer label

        # --- Merging Guides ---
        merge_box = finalize_box.box() # Sub-box for merging
        merge_box.label(text="Merge Guide Groups:")
        if current_perspective_type != 'NONE' and \
           current_perspective_type in PERSPECTIVE_OT_merge_specific_guides.GUIDE_GROUP_DEFS:
        
            type_specific_merge_col = merge_box.column(align=True) # Use a column for better button layout
            guide_groups_for_type = PERSPECTIVE_OT_merge_specific_guides.GUIDE_GROUP_DEFS[current_perspective_type]
            
            for group_id_key, (_, name_suggestion_part) in guide_groups_for_type.items():
                label_text = name_suggestion_part.replace(current_perspective_type.replace('_',''), "").replace("_Lines", "").replace("Lines","").replace("_", " ").strip().title()
                if not label_text: label_text = group_id_key.replace("_LINES", "").replace("_", " ").strip().title()
                
                op = type_specific_merge_col.operator(
                    PERSPECTIVE_OT_merge_specific_guides.bl_idname, 
                    text=f"Merge {label_text} ({current_perspective_type.replace('_', ' ')})" # Added type for clarity
                )
                op.group_identifier = group_id_key
        
            op_all_current = merge_box.operator(
                PERSPECTIVE_OT_merge_specific_guides.bl_idname, 
                text=f"Merge ALL {current_perspective_type.replace('_', ' ').title()} Guides"
            )
            op_all_current.group_identifier = "ALL_CURRENT_TYPE"
        else:
            merge_box.label(text="No specific merge groups for current mode.", icon='INFO')


        finalize_box.operator(PERSPECTIVE_OT_merge_guides.bl_idname, text="Merge All Visible Guide Objects", icon='OBJECT_DATAMODE')
        finalize_box.separator()
    
         # --- Show/Hide Guide Groups Section ---
        show_hide_box = finalize_box.box() # Sub-box for visibility
        show_hide_box.label(text="Toggle Guide Group Visibility:")
        col_sh = show_hide_box.column(align=True)

        if current_perspective_type != 'NONE' and current_perspective_type in PERSPECTIVE_OT_merge_specific_guides.GUIDE_GROUP_DEFS:
              guide_groups = PERSPECTIVE_OT_merge_specific_guides.GUIDE_GROUP_DEFS[current_perspective_type]
              for group_key, (prefixes, name_part) in guide_groups.items():
                  if prefixes: # Ensure there's a prefix to use
                     toggle_label = name_part.replace('_Lines','').replace(current_perspective_type.replace('_',''),"").replace("_", " ").strip().title()
                     if not toggle_label: toggle_label = group_key.replace("_LINES", "").replace("_", " ").strip().title()
                     
                     op_sh = col_sh.operator(
                         PERSPECTIVE_OT_toggle_guide_visibility.bl_idname, 
                         text=f"Toggle {toggle_label}"
                         # Icon could be made dynamic based on current visibility state of the group later
                     )
                     op_sh.group_prefix = prefixes[0] 
        else:
            col_sh.label(text="Select a perspective type for visibility toggles.", icon='INFO')


    # --- Main draw method for the panel ---
    def draw(self, context):
        layout = self.layout
        
        if not hasattr(context.scene, "perspective_tool_settings_splines") or \
           not context.scene.perspective_tool_settings_splines:
            layout.label(text="Error: Rogue Perspective AI - Properties not initialized.", icon='ERROR')
            return
        
        ts = context.scene.perspective_tool_settings_splines

        # --- Mode Selector ---
        layout.prop(ts, "current_perspective_type", text="Mode")
        layout.separator()

        # --- Horizon Line Section ---
        box_hz = layout.box()
        col_hz_main = box_hz.column()
        col_hz_main.label(text="Horizon Line Control:")
        row_hz_ctrl = col_hz_main.row(align=True)
        row_hz_ctrl.prop(ts, "horizon_y_level", text="Horizon Z")
        row_hz_ctrl.operator("perspective_splines.generate_horizon", text="Set/Update", icon='CON_SIZELIMIT')
        
        col_hz_props = col_hz_main.column(align=True)
        col_hz_props.prop(ts, "horizon_line_length")
        col_hz_props.prop(ts, "horizon_line_thickness")
        col_hz_props.prop(ts, "horizon_line_color", text="Color & Alpha")
        col_hz_main.operator("perspective_splines.clear_horizon", text="Clear Horizon Elements", icon='X')
        layout.separator()

        # --- Vanishing Point Controls ---
        box_vps = layout.box()
        col_vps_main = box_vps.column()
        col_vps_main.label(text="Main Vanishing Points (VPs):")
        
        col_vps_main.prop(ts, "show_main_vps") # Toggle for Main VP Visibility
        
        row_vps_ops = col_vps_main.row(align=True)
        row_vps_ops.operator("perspective_splines.add_vp_empty", text="Add Generic VP", icon='ADD')
        row_vps_ops.operator(
            "perspective_splines.remove_selected_helper_empty",
            text="Remove Sel. VP/Ctrl",
            icon='REMOVE'
        )



        if ts.show_main_vps:
            vps_to_display = []
            # Determine which VPs are relevant to the current mode
            if ts.current_perspective_type != 'NONE':
                if ts.current_perspective_type == 'THREE_POINT':
                    vps_to_display.extend(get_vanishing_points('THREE_POINT_H'))
                    vps_to_display.extend(get_vanishing_points('THREE_POINT_V'))
                elif ts.current_perspective_type in VP_TYPE_SPECIFIC_PREFIX_MAP:
                     vps_to_display = get_vanishing_points(ts.current_perspective_type)
            # If no specific mode or VPs for that mode, don't try to list (get_vanishing_points might return all)
            # This prevents listing unrelated VPs when a specific mode is active.
            # If mode is NONE, we might want to show all VPs that exist.
            if ts.current_perspective_type == 'NONE':
                vps_to_display = get_vanishing_points()


            if vps_to_display:
                vp_display_box = col_vps_main.box()
                # vp_display_box.label(text="Relevant VPs:") # Label can be optional
                for vp_obj in vps_to_display:
                    if vp_obj.name not in bpy.data.objects: continue # Stale reference check

                    row_vp_item = vp_display_box.row(align=True)
                    row_vp_item.label(text=f"{vp_obj.name}", icon='EMPTY_DATA')
                    loc_row = row_vp_item.row(align=True)
                    loc_row.prop(vp_obj, "location", index=0, text="X")
                    loc_row.prop(vp_obj, "location", index=1, text="Y")
                    loc_row.prop(vp_obj, "location", index=2, text="Z")
            elif ts.current_perspective_type != 'NONE': # Only show "no VPs found" if a mode is active
                col_vps_main.label(text=f"No VPs found for {ts.current_perspective_type.replace('_', ' ')} mode.", icon='INFO')
        layout.separator()

        # --- Guide Lines General Appearance ---
        box_guides_app = layout.box()
        col_guides_app_main = box_guides_app.column()
        col_guides_app_main.label(text="Guide Lines General Appearance:")
        col_guides_props = col_guides_app_main.column(align=True)
        col_guides_props.prop(ts, "guide_curves_thickness")
        col_guides_props.prop(ts, "guide_curves_opacity")
        col_guides_app_main.operator("perspective_splines.clear_just_guides", text="Clear All Guide Lines", icon='BRUSH_DATA')
        layout.separator()

        # --- Perspective-specific Line Generation Settings ---
        # These call the methods that draw the UI for 1P, 2P, 3P, FishEye *line generation* settings
        if ts.current_perspective_type == 'ONE_POINT':
            self.draw_one_point_panel(context, layout, ts)
        elif ts.current_perspective_type == 'TWO_POINT':
            self.draw_two_point_panel(context, layout, ts)
        elif ts.current_perspective_type == 'THREE_POINT':
            self.draw_three_point_panel(context, layout, ts)
        elif ts.current_perspective_type == 'FISH_EYE':
            self.draw_fish_eye_panel(context, layout, ts)
        
        if ts.current_perspective_type != 'NONE':
             layout.separator() # Add separator after the mode-specific panel

        # Sub-panels for Extraction, Grids, Trimmer are drawn automatically by Blender
        # if their bl_parent_id is "VIEW3D_PT_rogue_perspective_ai".

        # --- Finalize Guides Section ---
        self.draw_finalize_guides_section(layout, context)
        layout.separator()

        # --- Camera Alignment ---
        box_cam = layout.box()
        col_cam_main = box_cam.column()
        col_cam_main.label(text="Camera Alignment:")
        col_cam_props = col_cam_main.column(align=True)
        col_cam_props.prop(ts, "camera_eye_height")
        col_cam_props.prop(ts, "camera_distance")
        col_cam_main.operator("perspective_splines.align_camera", icon='CAMERA_DATA')
        layout.separator()
        
        # --- Master Clear Button ---
        layout.operator("perspective_splines.clear_all", text="Clear ALL Perspective Data", icon='TRASH')

    # --- Perspective-specific sub-panel drawing methods for line generation ---
    # Ensure these methods are correctly indented as part of this class
    # (They were present in your original script)

    def draw_one_point_panel(self, context, parent_layout, settings): 
        box = parent_layout.box() 
        col = box.column(align=True)
        col.label(text="One-Point Line Settings:") # Clarified this is for line settings
        col.prop(settings, "one_point_vp_empty_color", text="VP Empty Color")
        col.separator()
        
        row_radial = col.row(align=True)
        row_radial.prop(settings, "one_point_draw_radial", text="Radial",toggle=True)
        if settings.one_point_draw_radial:
            row_radial.prop(settings, "one_point_grid_density_radial", text="Density")
        
        row_ortho_x = col.row(align=True)
        row_ortho_x.prop(settings, "one_point_draw_ortho_x", text="Horizontal", toggle=True)
        if settings.one_point_draw_ortho_x:
            row_ortho_x.prop(settings, "one_point_grid_density_ortho_x", text="Density")

        row_ortho_y = col.row(align=True)
        row_ortho_y.prop(settings, "one_point_draw_ortho_y", text="Vertical", toggle=True)
        if settings.one_point_draw_ortho_y:
            row_ortho_y.prop(settings, "one_point_grid_density_ortho_y", text="Density")
        
        if settings.one_point_draw_ortho_x or settings.one_point_draw_ortho_y or settings.one_point_draw_radial:
             col.prop(settings, "one_point_grid_extent")
             col.prop(settings, "one_point_line_extension")

        box.operator("perspective_splines.generate_one_point", text="Generate/Update 1P Lines", icon='CURVE_PATH')

    def draw_two_point_panel(self, context, parent_layout, settings):
        box = parent_layout.box()
        col = box.column(align=True)
        col.label(text="Two-Point Line Settings:")
        
        col.label(text="VP Empty Colors:")
        row_vp_colors = col.row(align=True)
        row_vp_colors.prop(settings, "two_point_vp1_empty_color", text="VP1")
        row_vp_colors.prop(settings, "two_point_vp2_empty_color", text="VP2")
        col.separator()
        
        col.prop(settings, "two_point_line_extension")
        col.separator()

        # VP1 Lines
        sub_box_vp1 = col.box()
        sub_box_vp1_row = sub_box_vp1.row(align=True)
        sub_box_vp1_row.label(text="VP1 Lines:")
        sub_box_vp1_row.prop(settings, "two_point_grid_density_vp1", text="Density")
        sub_box_vp1.operator("perspective_splines.generate_2p_vp1_lines", text="Draw/Update VP1 Lines")

        # VP2 Lines
        sub_box_vp2 = col.box()
        sub_box_vp2_row = sub_box_vp2.row(align=True)
        sub_box_vp2_row.label(text="VP2 Lines:")
        sub_box_vp2_row.prop(settings, "two_point_grid_density_vp2", text="Density")
        sub_box_vp2.operator("perspective_splines.generate_2p_vp2_lines", text="Draw/Update VP2 Lines")
        
        # Vertical Lines
        sub_box_vert = col.box()
        sub_box_vert_row = sub_box_vert.row(align=True)
        sub_box_vert_row.label(text="Vertical Lines:")
        sub_box_vert_row.prop(settings, "two_point_grid_density_vertical", text="Density")
        if settings.two_point_grid_density_vertical > 0:
            sub_box_vert.prop(settings, "two_point_verticals_x_spacing_factor")
            sub_box_vert.prop(settings, "two_point_grid_height")
            sub_box_vert.prop(settings, "two_point_grid_depth_offset")
        sub_box_vert.operator("perspective_splines.generate_2p_vertical_lines", text="Draw/Update Vertical Lines")
        
        col.separator()
        col.operator("perspective_splines.create_2p_vps_if_needed", text="Ensure 2P VPs & Horizon Exist", icon='EMPTY_AXIS')

    def draw_three_point_panel(self, context, parent_layout, settings):
        box = parent_layout.box()
        col = box.column(align=True)
        col.label(text="Three-Point Line Settings:")
    
        col.label(text="VP Empty Colors:")
        row_vp_colors = col.row(align=True)
        row_vp_colors.prop(settings, "three_point_vp_h1_empty_color", text="H1")
        row_vp_colors.prop(settings, "three_point_vp_h2_empty_color", text="H2")
        row_vp_colors.prop(settings, "three_point_vp_v_empty_color", text="V")
        col.separator()
    
        col.prop(settings, "three_point_line_extension")
        col.separator()

        col.label(text="Guide Densities:")
        row_density1 = col.row(align=True)
        row_density1.prop(settings, "three_point_vp_h1_density", text="H1")
        row_density1.prop(settings, "three_point_vp_h2_density", text="H2")
        col.prop(settings, "three_point_vp_v_density", text="V Density")
        col.separator()

        col_ops = col.column(align=True) # Group operators
        col_ops.operator("perspective_splines.generate_3p_h1_lines", text="Draw/Update H_VP1 Lines")
        col_ops.operator("perspective_splines.generate_3p_h2_lines", text="Draw/Update H_VP2 Lines")
        col_ops.operator("perspective_splines.generate_3p_v_lines", text="Draw/Update V_VP Lines")
        col.separator()
        col.operator("perspective_splines.create_3p_vps_if_needed", text="Ensure 3P VPs & Horizon Exist", icon='EMPTY_AXIS')

    def draw_fish_eye_panel(self, context, parent_layout, settings):
        box = parent_layout.box()
        col = box.column(align=True)
        col.label(text="Fish Eye Line Settings:")
        col.prop(settings, "fish_eye_vp_empty_color", text="VP Empty Color")
        col.separator()
        col.prop(settings, "fish_eye_grid_radius")
        
        row_grid_lines = col.row(align=True)
        row_grid_lines.prop(settings, "fish_eye_grid_radial", text="Longitudes")
        row_grid_lines.prop(settings, "fish_eye_grid_concentric", text="Latitudes")
        
        col.prop(settings, "fish_eye_segments_per_curve")
        col.prop(settings, "fish_eye_horizontal_scale")
        col.prop(settings, "fish_eye_draw_latitude", toggle=True)
        
        box.operator("perspective_splines.generate_fish_eye", text="Generate/Update Fish Eye Lines", icon='MESH_UVSPHERE')
    
        


# -----------------------------------------------------------
# Depsgraph Handler
# -----------------------------------------------------------
_depsgraph_handler_active_splines = True # Global flag to prevent re-entrancy

# -----------------------------------------------------------
# Depsgraph Handler
# -----------------------------------------------------------
_depsgraph_handler_active_splines = True # Global flag to prevent re-entrancy

# -----------------------------------------------------------
# Depsgraph Handler
# -----------------------------------------------------------
_depsgraph_handler_active_splines = True # Global flag to prevent re-entrancy

def perspective_depsgraph_handler_splines(scene, depsgraph):
    global _depsgraph_handler_active_splines
    if not _depsgraph_handler_active_splines or not bpy.context.screen:
        return
    if not hasattr(scene, 'perspective_tool_settings_splines') or scene.perspective_tool_settings_splines is None:
        return

    context_for_update = bpy.context
    if context_for_update.scene != scene:
        valid_context_found = False
        for window in bpy.context.window_manager.windows:
            if window.screen:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        for region in area.regions:
                            if region.type == 'WINDOW':
                                try:
                                    override = {'window': window, 'area': area, 'region': region, 'screen': window.screen, 'scene': scene}
                                    context_for_update = bpy.context.temp_override(**override)
                                    valid_context_found = True
                                    break
                                except Exception:
                                    pass
                        if valid_context_found: break
            if valid_context_found: break
        if not valid_context_found:
            return

    tool_settings = scene.perspective_tool_settings_splines
    needs_horizon_recalc = False
    empties_used_for_aid_lines_transformed = False

    _depsgraph_handler_active_splines = False
    try:
        for update in depsgraph.updates:
            if not isinstance(update.id, bpy.types.Object) or not update.is_updated_transform:
                continue
            
            obj_being_updated = update.id
            obj_name = obj_being_updated.name

            # --- Main Horizon Line Recalculation Logic ---
            if obj_name == HORIZON_CTRL_OBJ_NAME:
                horizon_ctrl_obj = scene.objects.get(HORIZON_CTRL_OBJ_NAME)
                if horizon_ctrl_obj:
                    new_z = horizon_ctrl_obj.location.z
                    if abs(tool_settings.horizon_y_level - new_z) > 0.001:
                        tool_settings.horizon_y_level = new_z
                    needs_horizon_recalc = True
            elif obj_name.startswith(VP_PREFIX) and not "_Aid" in obj_name : # Main VPs, not aid empties
                vp_obj_moved = scene.objects.get(obj_name)
                if vp_obj_moved:
                    current_type = tool_settings.current_perspective_type
                    if current_type == 'ONE_POINT' and vp_obj_moved.name.startswith(VP_TYPE_SPECIFIC_PREFIX_MAP['ONE_POINT']):
                        if abs(tool_settings.horizon_y_level - vp_obj_moved.location.z) > 0.001:
                            tool_settings.horizon_y_level = vp_obj_moved.location.z
                        needs_horizon_recalc = True
                    elif current_type == 'TWO_POINT' and vp_obj_moved.name.startswith(VP_TYPE_SPECIFIC_PREFIX_MAP['TWO_POINT']):
                        needs_horizon_recalc = True
                    elif current_type == 'THREE_POINT' and vp_obj_moved.name.startswith(VP_TYPE_SPECIFIC_PREFIX_MAP['THREE_POINT_H']):
                        needs_horizon_recalc = True
            
            # --- Visual Aid Line Update Logic ---
            if tool_settings.show_extraction_helper_lines and \
               obj_being_updated.type == 'EMPTY' and \
               "_Aid" in obj_name: # Only consider specifically named aid empties

                is_selected_in_context = False
                try:
                    if obj_being_updated in context_for_update.selected_objects:
                        is_selected_in_context = True
                except (AttributeError, ReferenceError):
                    pass

                if is_selected_in_context:
                    current_mode_for_aids = tool_settings.current_perspective_type
                    
                    if current_mode_for_aids == 'ONE_POINT' and "1P_Aid" in obj_name:
                        # Count how many specifically "1P_Aid" empties are selected
                        relevant_selected_helpers = [
                            e for e in context_for_update.selected_objects 
                            if e.type == 'EMPTY' and "1P_Aid" in e.name 
                        ]
                        if len(relevant_selected_helpers) == 4: # Only trigger if the group of 4 is involved
                            empties_used_for_aid_lines_transformed = True
                    
                    elif current_mode_for_aids == 'TWO_POINT':
                        if "2P_VP1_Aid" in obj_name:
                            relevant_selected_helpers_vp1 = [e for e in context_for_update.selected_objects if e.type == 'EMPTY' and "2P_VP1_Aid" in e.name]
                            if len(relevant_selected_helpers_vp1) == 4:
                                empties_used_for_aid_lines_transformed = True
                        elif "2P_VP2_Aid" in obj_name:
                            relevant_selected_helpers_vp2 = [e for e in context_for_update.selected_objects if e.type == 'EMPTY' and "2P_VP2_Aid" in e.name]
                            if len(relevant_selected_helpers_vp2) == 4:
                                empties_used_for_aid_lines_transformed = True
                                
                    elif current_mode_for_aids == 'THREE_POINT':
                        # Example for H1, extend for H2 and V
                        if "3P_H1_Aid" in obj_name: # Assuming you'll name them like this
                            relevant_selected_helpers_3p_h1 = [e for e in context_for_update.selected_objects if e.type == 'EMPTY' and "3P_H1_Aid" in e.name]
                            if len(relevant_selected_helpers_3p_h1) == 4:
                                empties_used_for_aid_lines_transformed = True
                        # Add similar checks for "3P_H2_Aid" and "3P_V_Aid" named empties

        # --- Apply Updates After Iterating ---
        if needs_horizon_recalc:
            try:
                update_dynamic_horizon_line_curve(context_for_update)
            except Exception as e:
                print(f"Depsgraph Error: Failed to update dynamic horizon line: {e}")

        if empties_used_for_aid_lines_transformed:
            try:
                print("DEBUG depsgraph: Triggering refresh_extraction_aid_lines due to aid empty transform.") # DEBUG
                refresh_extraction_aid_lines(context_for_update, from_selection_change=False) # from_selection_change is False here
            except Exception as e:
                 print(f"Depsgraph Error: Failed to refresh extraction aid lines: {e}")

    except Exception as e:
        print(f"Error in perspective_depsgraph_handler_splines main loop: {e}")
    finally:
        _depsgraph_handler_active_splines = True

# -----------------------------------------------------------
# Registration
# -----------------------------------------------------------
# Original relevant part:
#    PERSPECTIVE_OT_merge_guides,
#    PERSPECTIVE_OT_merge_and_convert_to_gpencil,
#    # Optionally, remove this if you don't want the old merge/convert functionality:
#    # PERSPECTIVE_OT_convert_to_grease_pencil,  <-- This was the old one
#    Rogue_Perspective_AI_PT_main,

# Change to include the new operator name:
# (This tuple is usually found near the end of your script, just before the register() and unregister() functions)

# (Near the end of your script)
# (Near the end of your script)
# (Near the end of your script)
# (Near the end of your script)
# Updated classes_splines tuple that includes the new operators

# Updated classes_splines tuple that includes the new operators

classes_splines = (
    # --- Property Group ---
    PerspectiveToolSettingsSplines,

    # --- Generation and Setup Operators ---
    PERSPECTIVE_OT_generate_horizon_spline,
    PERSPECTIVE_OT_add_vanishing_point_empty,
    PERSPECTIVE_OT_generate_one_point_splines,
    PERSPECTIVE_OT_create_2p_vps_if_needed,
    PERSPECTIVE_OT_generate_2p_vp1_lines,
    PERSPECTIVE_OT_generate_2p_vp2_lines,
    PERSPECTIVE_OT_generate_2p_vertical_lines,
    PERSPECTIVE_OT_create_3p_vps_if_needed,
    PERSPECTIVE_OT_generate_3p_h1_lines,
    PERSPECTIVE_OT_add_3p_h_vp1_helpers,
    PERSPECTIVE_OT_extract_3p_h_vp1_from_empties,
    
    # --- New 3P Operators for VP2 and Vertical ---
    PERSPECTIVE_OT_add_3p_h_vp2_helpers,
    PERSPECTIVE_OT_extract_3p_h_vp2_from_empties,
    PERSPECTIVE_OT_add_3p_v_vp_helpers,
    PERSPECTIVE_OT_extract_3p_v_from_empties,
    PERSPECTIVE_OT_generate_3p_h2_lines,  # <-- Add this line!
    PERSPECTIVE_OT_generate_3p_v_lines,

    # --- Other Generation Operators ---
    PERSPECTIVE_OT_generate_fish_eye_splines,
    PERSPECTIVE_OT_align_camera_splines,
    PERSPECTIVE_OT_create_box_grid,
    PERSPECTIVE_OT_clip_guides_to_camera,

    # --- Extraction (from empties) Operators for 1P and 2P ---
    PERSPECTIVE_OT_add_1p_extraction_empties,
    PERSPECTIVE_OT_extract_1p_from_selected_empties,
    PERSPECTIVE_OT_add_2p_vp1_helpers,
    PERSPECTIVE_OT_extract_2p_vp1_from_empties,
    PERSPECTIVE_OT_add_2p_vp2_helpers,
    PERSPECTIVE_OT_extract_2p_vp2_from_empties,
    
    # --- Refresh and Helper Management Operators ---
    PERSPECTIVE_OT_refresh_extraction_aids,
    PERSPECTIVE_OT_toggle_all_helpers,
    PERSPECTIVE_OT_delete_all_helpers,
    PERSPECTIVE_OT_select_helper_empties,

    # --- Clearing and Merging Operators ---
    PERSPECTIVE_OT_clear_grid_planes,
    PERSPECTIVE_OT_remove_selected_helper_empty,
    PERSPECTIVE_OT_clear_type_guides_splines,
    PERSPECTIVE_OT_clear_just_guides,
    PERSPECTIVE_OT_clear_horizon_spline,
    PERSPECTIVE_OT_clear_all_perspective_splines,
    PERSPECTIVE_OT_merge_specific_guides,
    PERSPECTIVE_OT_merge_guides,
    PERSPECTIVE_OT_toggle_guide_visibility,

    # --- UI Panels ---
    Rogue_Perspective_AI_PT_main,
    VIEW3D_PT_rogue_perspective_grids,
    VIEW3D_PT_rogue_perspective_trimmer,
    VIEW3D_PT_perspective_extraction,
)


def register():
    global _depsgraph_handler_active_splines, previous_perspective_type_on_switch
    for cls in classes_splines:
        try:
            bpy.utils.register_class(cls)
        except ValueError as e:
            print(f"Warning: Class {cls.__name__} already registered or error: {e}")

    try:
        bpy.types.Scene.perspective_tool_settings_splines = bpy.props.PointerProperty(type=PerspectiveToolSettingsSplines)
    except TypeError as e:
        print(f"Warning: perspective_tool_settings_splines already exists on Scene type: {e}")

    # Append the depsgraph handler if not already present
    if perspective_depsgraph_handler_splines not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(perspective_depsgraph_handler_splines)

    _depsgraph_handler_active_splines = True
    # The global previous_perspective_type_on_switch default is already set (typically to 'NONE')
    print("Rogue Perspective AI Registered.")


def unregister():
    global _depsgraph_handler_active_splines
    _depsgraph_handler_active_splines = False  # Disable depsgraph handler

    if perspective_depsgraph_handler_splines in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(perspective_depsgraph_handler_splines)

    if hasattr(bpy.types.Scene, 'perspective_tool_settings_splines'):
        try:
            del bpy.types.Scene.perspective_tool_settings_splines
        except Exception as e:
            print(f"Warning: Could not delete perspective_tool_settings_splines from Scene: {e}")

    for cls in reversed(classes_splines):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError as e:
            print(f"Warning: Could not unregister class {cls.__name__}: {e}")
        except Exception as e:
            print(f"Error unregistering class {cls.__name__}: {e}")

    print("Rogue Perspective AI Unregistered.")


if __name__ == "__main__":
    # Useful for testing inside Blender's text editor: unregister if already registered then register.
    if hasattr(bpy.types, "Rogue_Perspective_AI_PT_main"):
        try:
            unregister()
        except Exception as e:
            print(f"Error during pre-emptive unregistration: {e}")
    try:
        register()
    except Exception as e:
        print(f"Error during registration: {e}")


