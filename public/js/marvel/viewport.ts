// The board locks pinch-zoom on purpose: the scene is already scaled to fit the
// window, and a two-finger gesture on it is a camera drag rather than a browser
// zoom. The panels drawn on top of the board - the menu/log and the game-over
// report - are plain text laid out at whatever size that scale left them, so
// they get the zoom back for as long as they are open.
export class Viewport {
    private static meta = document.querySelector('meta[name="viewport"]') as HTMLMetaElement | null
    private static readonly base = 'width=device-width,height=device-height,viewport-fit=cover,initial-scale=1'
    private static readonly locked = `${Viewport.base},maximum-scale=1,user-scalable=0`
    private static readonly zoomable = `${Viewport.base},maximum-scale=5,user-scalable=1`

    // Panels are independent: the game-over report can go up while the menu is
    // already open, and closing one must not re-lock the other.
    private static zoom_panels = new Set<string>()

    static setZoomAllowed(panel: string, allowed: boolean) {
        if( allowed ) {
            Viewport.zoom_panels.add(panel)
        } else {
            Viewport.zoom_panels.delete(panel)
        }
        Viewport.apply()
    }

    private static apply() {
        if( !Viewport.meta ) {
            return
        }
        const content = Viewport.zoom_panels.size > 0 ? Viewport.zoomable : Viewport.locked
        if( Viewport.meta.content != content ) {
            Viewport.meta.content = content
        }
    }
}
