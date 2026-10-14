#include <xcb/xcb.h>
#include <xcb/present.h>
#include <stdio.h>
#include <stdlib.h>
/* Serial real pixmap presents: NotifyMSC alone can return nonprogressing UST.
 * This measures COPY completion pacing, not encoder output or physical scanout. */
int main(void) {
    xcb_connection_t *c = xcb_connect(NULL, NULL);
    if (xcb_connection_has_error(c)) return 2;
    xcb_screen_t *s = xcb_setup_roots_iterator(xcb_get_setup(c)).data;
    xcb_window_t w = xcb_generate_id(c);
    uint32_t value = s->black_pixel;
    xcb_create_window(c, XCB_COPY_FROM_PARENT, w, s->root, 0, 0, 160, 160, 0,
                      XCB_WINDOW_CLASS_INPUT_OUTPUT, s->root_visual, XCB_CW_BACK_PIXEL, &value);
    xcb_map_window(c, w);
    xcb_pixmap_t pix = xcb_generate_id(c);
    xcb_create_pixmap(c, s->root_depth, pix, w, 160, 160);
    xcb_gcontext_t gc = xcb_generate_id(c);
    xcb_create_gc(c, gc, pix, XCB_GC_FOREGROUND, &value);
    xcb_rectangle_t rect = {0, 0, 160, 160};
    xcb_present_event_t eid = xcb_generate_id(c);
    xcb_present_select_input(c, eid, w, XCB_PRESENT_EVENT_MASK_COMPLETE_NOTIFY);
    xcb_generic_error_t *error = NULL;
    xcb_present_query_version_reply_t *version = xcb_present_query_version_reply(
        c, xcb_present_query_version(c, 1, 2), &error);
    if (!version || error) return 3;
    free(version);
    xcb_special_event_t *special = xcb_register_for_special_xge(c, &xcb_present_id, eid, NULL);
    uint64_t first = 0, last = 0, msc = 0;
    for (int i = 0; i < 180; i++) {
        value = (i % 2) ? s->white_pixel : s->black_pixel;
        xcb_change_gc(c, gc, XCB_GC_FOREGROUND, &value);
        xcb_poly_fill_rectangle(c, pix, gc, 1, &rect);
        xcb_present_pixmap(c, w, pix, i, 0, 0, 0, 0, 0, 0, 0,
                           XCB_PRESENT_OPTION_COPY, msc ? msc + 1 : 0, 0, 0, 0, NULL);
        xcb_flush(c);
        xcb_generic_event_t *event = xcb_wait_for_special_event(c, special);
        if (!event) return 4;
        xcb_present_complete_notify_event_t *done = (void *)event;
        if (done->event_type != XCB_PRESENT_COMPLETE_NOTIFY || done->kind != XCB_PRESENT_COMPLETE_KIND_PIXMAP || done->serial != (unsigned)i || done->ust == 0) return 5;
        if (i == 0) first = done->ust;
        last = done->ust;
        msc = done->msc;
        free(event);
    }
    if (last <= first) return 6;
    printf("{\"copy_Hz\": %.3f, \"intervals\": 179, \"ust_first\": %llu, \"ust_last\": %llu}\n",
           179000000.0 / (last - first), (unsigned long long)first, (unsigned long long)last);
    xcb_disconnect(c);
    return 0;
}
