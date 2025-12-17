import requests
import yaml


class rjapi:

    def __init__(self, config_file = None):
        if config_file is None:
            config_file = "config.yaml"
        self.config = self.__load_config(config_file)
        self.__search_endpoint = "https://brn-ybus-pubapi.sa.cz/restapi/routes/search/simple?departureDate={}&fromLocationId={}&toLocationId={}&fromLocationType={}&toLocationType={}&tariffs={}"
        self.__train_enpoint = "https://brn-ybus-pubapi.sa.cz/restapi/routes/{0}/simple?routeId={0}&fromStationId={1}&toStationId={2}&tariffs={3}"
        self.__shop_link = "https://regiojet.cz/?departureDate={}&fromLocationId={}&toLocationId={}&fromLocationType={}&toLocationType={}&tariffs={}"
        self.__last_matched_time = None
    

    def __load_config(self, config_file):
        with open(config_file, "r") as f:
            cfg = yaml.safe_load(f)
        if type(cfg["tariff"]) is list:
            cfg["quantity"] = len(cfg["tariff"])
            cfg["tariff"] = "&tariffs=".join(cfg["tariff"])
        else:
            cfg["quantity"] = 1
        if type(cfg["preffered_class"]) is str:
            cfg["preffered_class"] = [cfg["preffered_class"]]
        time_value = cfg.get("time")
        if isinstance(time_value, str):
            cfg["time"] = [time_value.strip()]
        elif isinstance(time_value, list):
            cfg["time"] = [str(t).strip() for t in time_value if str(t).strip()]
        else:
            raise ValueError("time must be a string or list of strings")
        if not cfg["time"]:
            raise ValueError("time must contain at least one value")
        return cfg
    

    def search_train(self, train):
        # Get all classes info for given train
        train_details = requests.get(self.__train_enpoint.format(train["id"], train["departureStationId"], train["arrivalStationId"], self.config["tariff"])).json()
        # Check max changes
        if len(train_details["sections"]) > self.config["max_changes"] + 1:
            return False
        # No preffered class
        if not self.config["preffered_class"]:
            return True
        # Find preffered class and check seat availability
        for i in train_details["priceClasses"]:
            if i["seatClassKey"] in self.config["preffered_class"] and i["freeSeatsCount"] >= self.config["quantity"]:
                return True
        return False


    def search_ticket(self):
        # Get all routes for given date
        day_trains = requests.get(self.__search_endpoint.format(self.config["date"], self.config["from"], self.config["to"], self.config["from_type"], self.config["to_type"], self.config["tariff"])).json()
        # No trains on given trains
        if "routes" not in day_trains:
            return False
        
        # Find trains with given time
        day_trains = day_trains["routes"]
        for tracked_time in self.config["time"]:
            datetime = self.config["date"] + "T" + tracked_time
            trains = []
            for i in day_trains:
                if datetime in i["departureTime"]:
                    trains.append(i)

            # No trains with given time
            if not trains:
                continue

            for train in trains:
                # Not enough tickets available or train not bookable
                if train["freeSeatsCount"] < self.config["quantity"] or not train["bookable"]:
                    continue

                # Seat available - max changes exceeded or preffered class not available
                if not self.search_train(train):
                    continue

                # Seat available
                self.__last_matched_time = tracked_time
                return True

        # No train with seats available
        return False


    def send_alert(self):
        # Craft data
        data = {
            "message" : "Tickets for {}T{} available!".format(self.config["date"], self.__last_matched_time or self.config["time"][0]),
            "action" : self.__shop_link.format(self.config["date"], self.config["from"], self.config["to"], self.config["from_type"], self.config["to_type"], self.config["tariff"])
        }
        # Send to notify.run
        requests.post("https://notify.run/"+self.config["notify_code"], data=data)  