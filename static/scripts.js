var wakeforms = document.getElementsByClassName("hostwake")

for (let i = 0; i < wakeforms.length; i++) {
    let evtSource = null;

    wakeforms[i].addEventListener('submit', async (e) => {
        const url = e.currentTarget.action;
        const status_row = document.getElementById(url);
        const status_cell = status_row.getElementsByTagName("td")[0]

        function update_status(status, error = null) {
            const new_class = status.toLowerCase();
            status_row.className = `status-${new_class}`;
            status_cell.innerText = status;

            if (error !== null) {
                console.error(error)
            }
        }

        e.preventDefault();

        if (evtSource) {
            evtSource.close();
            evtSource = null;
        }

        try {
            const response = await fetch(url, {
                headers: new Headers({ "Accept": "application/json" })
            });
            const data = await response.json();

            if (!response.ok) {
                update_status("Error", data.message || "Request failed")
                return;
            }

            if (data.service_status == "online") {
                update_status("Online")
                return;
            }

            if (data.service_status == "error") {
                update_status("Error", data.message || "Unknown error")
                return;
            }

            update_status("Starting")

            const event_url = `//${window.location.host}/online/?url=${encodeURIComponent(url)}`;
            evtSource = new EventSource(event_url);

            evtSource.addEventListener("online", (event) => {
                const data = JSON.parse(event.data);

                if (data.online === true) {
                    evtSource.close();
                    evtSource = null;
                    update_status("Online")
                }
            });

            evtSource.addEventListener("error", (event) => {
                const data = JSON.parse(event.data);

                evtSource.close();
                evtSource = null;
                update_status("Error", data.msg || "SSE connection error")
            });
        } catch (error) {
            update_status("Error", "Could not parse response")
        }
    });
}