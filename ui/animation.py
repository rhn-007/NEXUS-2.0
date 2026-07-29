import threading
import time
import sys

from ui.status import get_status


class NexusAnimation:


    def __init__(self):

        self.running = False

        self.thread = None



        self.frames = [

            "○──○──●",

            "○──●──○",

            "●──○──○"

        ]



    def start(self):


        if self.running:

            return


        self.running = True


        self.thread = threading.Thread(

            target=self.loop,

            daemon=True

        )


        self.thread.start()



    def loop(self):


        index = 0


        while self.running:


            status = get_status()



            if status:


                frame = self.frames[index]


                sys.stdout.write(

                    f"\r[NEXUS] {frame} {status}..."

                )


                sys.stdout.flush()



                index = (

                    index + 1

                ) % len(self.frames)



            time.sleep(0.3)



    def stop(self):


        self.running = False



        if self.thread:

            self.thread.join(
                timeout=1
            )


        sys.stdout.write(
            "\r" + " " * 80 + "\r"
        )

        sys.stdout.flush()



animation = NexusAnimation()
