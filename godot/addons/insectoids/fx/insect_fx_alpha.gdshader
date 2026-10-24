shader_type spatial;

// The insects' flat effects (the spider's web snare and silk thread, the centipede's burrow hole): unlit, alpha
// blended, both faces, no depth write: the texture times the instance's tint, which each effect sets to fade itself
// (GeometryInstance3D.set_instance_shader_parameter("tint", colour)). Unity: SpiderFx.AlphaMaterial (URP
// Particles/Unlit, tinted through a MaterialPropertyBlock).
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled;

uniform sampler2D albedo_texture : source_color, hint_default_white, filter_linear_mipmap_anisotropic, repeat_disable;
instance uniform vec4 tint : source_color = vec4(1.0);

void fragment() {
	vec4 c = texture(albedo_texture, UV) * tint;
	ALBEDO = c.rgb;
	ALPHA = c.a;
}
