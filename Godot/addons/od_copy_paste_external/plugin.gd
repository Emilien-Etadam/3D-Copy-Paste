@tool
extends EditorPlugin
# Editor glue for OD_CopyPasteExternal: two Tool-menu entries wrapping the
# core logic in od_copy_paste.gd. See ../../README.md for usage.

const ODCopyPaste := preload("od_copy_paste.gd")

const COPY_LABEL := "OD Copy To External"
const PASTE_LABEL := "OD Paste From External"


func _enter_tree() -> void:
	add_tool_menu_item(COPY_LABEL, _on_copy)
	add_tool_menu_item(PASTE_LABEL, _on_paste)


func _exit_tree() -> void:
	remove_tool_menu_item(COPY_LABEL)
	remove_tool_menu_item(PASTE_LABEL)


func _on_copy() -> void:
	var nodes := EditorInterface.get_selection().get_selected_nodes()
	print("OD_CopyPasteExternal: " + ODCopyPaste.copy_selection(nodes))


func _on_paste() -> void:
	var result = ODCopyPaste.paste_from_file()
	if result is String:
		print("OD_CopyPasteExternal: " + result)
		return
	var mesh_instance: MeshInstance3D = result
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		print("OD_CopyPasteExternal: open a 3D scene first")
		mesh_instance.free()
		return
	root.add_child(mesh_instance)
	mesh_instance.owner = root
	EditorInterface.get_selection().clear()
	EditorInterface.get_selection().add_node(mesh_instance)
	print("OD_CopyPasteExternal: pasted %d surfaces into the scene" %
		mesh_instance.mesh.get_surface_count())
