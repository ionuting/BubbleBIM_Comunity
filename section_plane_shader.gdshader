shader_type spatial;

uniform vec3 plane_origin;
uniform vec3 plane_normal;
uniform bool active = true;
uniform vec4 contour_color : hint_color = vec4(1.0, 1.0, 0.0, 1.0); // Yellow for contours

void fragment() {
	if (active) {
		vec3 pos = WORLD_POS;
		float d = dot(pos - plane_origin, plane_normal);
		if (d > 0.0) {
			discard; // Discard fragments above the plane
		}

		// Highlight the intersection contour
		float contour_width = 0.01; // Thickness of the contour
		if (abs(d) < contour_width) {
			ALBEDO = contour_color.rgb;
			return;
		}
	}
}