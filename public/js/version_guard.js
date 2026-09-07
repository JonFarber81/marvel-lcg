/* Tells the server that a request came from page script, and acts on the 409 it
   answers with when this page is older than the server.

   Every route is version-checked, and a stale one used to be answered with the
   version-mismatch *page* - fine for the address bar, but a fetch() caller got
   a document where it expected JSON and died in JSON.parse, naming a "<" and
   not the real problem. The server now answers those callers with
   409 {"error": "version_mismatch"}, which it can only recognise if they say
   who they are, so this marks each one on the way out.

   A page only ever sees that 409 if the build changed under it - the server was
   restarted on a new version while this tab stayed open - so the fix is to
   reload: the navigation is not a fetch, and gets the page that explains it. */
(() => {
    const nativeFetch = window.fetch
    let reloading = false

    /** @param {RequestInfo|URL} input */
    function isSameOrigin(input) {
        try {
            const url = new URL(input instanceof Request ? input.url : String(input), location.href)
            return url.origin === location.origin
        } catch {
            return false
        }
    }

    window.fetch = async function (input, init) {
        if (!isSameOrigin(input)) {
            return nativeFetch(input, init)
        }
        const request = new Request(input, init)
        request.headers.set('X-Requested-With', 'fetch')

        const response = await nativeFetch(request)
        if (response.status != 409) {
            return response
        }
        // Read the copy, so a caller that handles its own 409 still gets a body.
        let body
        try {
            body = await response.clone().json()
        } catch {
            return response
        }
        if (body?.error != 'version_mismatch') {
            return response
        }
        if (!reloading) {
            reloading = true
            location.reload()
        }
        throw new Error(`This page is older than the server (now ${body.version}). Reloading.`)
    }
})()
