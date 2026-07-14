

var wakeforms = document.getElementsByClassName("hostwake")

for (let i = 0; i < wakeforms.length; i++) {

    wakeforms[i].addEventListener('submit', (e) => {

        e.preventDefault();
        const url = e.currentTarget.action;

        var event_url = `//${window.location.host}/online/?url=${encodeURIComponent(url)}`;
        const evtSource = new EventSource(event_url);

        evtSource.addEventListener("online", (event) => {
            var data = JSON.parse(event.data)
            if (data.online === true) {
                evtSource.close();
                const status = document.getElementById(url);
                status.innerHTML = '<td style="color:rgb(19, 242, 119)">Online</td>';
            }
        })

        evtSource.addEventListener("error", (event) => {
            var data = JSON.parse(event.data);

            evtSource.close();
            const status = document.getElementById(url);
            status.innerHTML = '<td style="color:rgb(242, 45, 19)">Error</td>';
        })

        fetch(url)
            .then(response => {
                const status = document.getElementById(url);
                status.innerHTML = '<td style="color:rgb(242, 153, 19)">Starting</td>';
            })
            .catch(error => {
                const status = document.getElementById(url);
                status.innerHTML = '<td style="color:rgb(242, 45, 19)">Error</td>';
            });
    });
}