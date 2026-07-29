"""
NEXUS Animation System

Safe terminal animation manager.

Rules:
- Animation only runs during processing
- Never fights with input()
- Clears its own line
- Thread safe
"""

import sys
import threading
import time

from ui.status import get_status



class NexusAnimation:


    def __init__(self):

        self.running = False

        self.thread = None

        self.lock = threading.RLock()


        self.frames = [

            "○──○──●",

            "○──●──○",

            "●──○──○",

            "○──●──○"

        ]



    # ==========================================
    # START
    # ==========================================

    def start(self):

        with self.lock:


            if self.running:

                return


            self.running = True


            self.thread = threading.Thread(

                target=self._loop,

                daemon=True

            )


            self.thread.start()



    # ==========================================
    # LOOP
    # ==========================================

    def _loop(self):

        index = 0


        while True:


            with self.lock:

                if not self.running:

                    break



            status = get_status()



            if status:


                frame = self.frames[index]


                sys.stderr.write(

                    f"\r[NEXUS] {frame} {status}..."

                )


                sys.stderr.flush()



                index = (

                    index + 1

                ) % len(self.frames)



            time.sleep(
                0.25
            )



    # ==========================================
    # CLEAR LINE
    # ==========================================

    def clear(self):


        sys.stderr.write(

            "\r" + (" " * 100) + "\r"

        )


        sys.stderr.flush()



    # ==========================================
    # STOP
    # ==========================================

    def stop(self):


        with self.lock:


            self.running = False



        if self.thread:


            self.thread.join(

                timeout=1

            )


            self.thread = None



        self.clear()





animation = NexusAnimation()
