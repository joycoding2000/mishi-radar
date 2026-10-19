//非空判断
function extendedIsEmpty(obj) {
  var regu = "^[ ]+$";
  var re = new RegExp(regu);
  if (
    typeof obj == "undefined" ||
    obj == null ||
    obj == "" ||
    re.test(obj) ||
    JSON.stringify(obj) == "{}"
  ) {
    return true;
  } else {
    return false;
  }
}

function Comparative(fir, las) {
  var _cls = "";
  if (Number(fir) > Number(las)) {
    _cls = "trending-up";
  } else if (Number(fir) < Number(las)) {
    _cls = "trending-down";
  } else {
    _cls = "trending";
  }
  return _cls;
}

function dateFormat(g) {
  var d = g.substring(0, 4);
  var e = g.substring(4, 6);
  var b = g.substring(6, 8);
  var a = g.substring(8, g.length - 4);
  var f = g.substring(g.length - 4, g.length - 2);
  var c = g.substring(g.length - 2);
  return d + "-" + e + "-" + b + "  " + a + ":" + f + ":" + c;
}

function convertDateToUTC(date) {
  var du_year = date.slice(0, 4);
  var du_month = date.slice(4, 6) - 1;
  var du_day = date.slice(6, 8);
  var du_hour = date.slice(8, 10);
  var du_minute = date.slice(10, 12);
  var du_second = date.slice(12, 14);
  return Number(
    Date.UTC(du_year, du_month, du_day, du_hour, du_minute, du_second)
  );
}

function convertWeek(num) {
  var week = "星期一";
  if (num == "Monday" || num == 1) {
    week = "星期一";
  } else if (num == "Tuesday" || num == 2) {
    week = "星期二";
  } else if (num == "Wednesday" || num == 3) {
    week = "星期三";
  } else if (num == "Thursday" || num == 4) {
    week = "星期四";
  } else if (num == "Friday" || num == 5) {
    week = "星期五";
  } else if (num == "Saturday" || num == 6) {
    week = "星期六";
  } else if (num == "Sunday" || num == 7) {
    week = "星期日";
  }
  return week;
}

/* 时间戳转换为日期字符串 */
function transformTime(timestamp) {
  if (timestamp) {
    var time = new Date(timestamp);
    var year = time.getFullYear();
    var month = time.getMonth() + 1;
    var day = time.getDate();
    return year + "" + addZero(month) + "" + addZero(day);
  } else {
    return "";
  }
}

/* 月、日不足10时，补0 */
function addZero(s) {
  return s < 10 ? "0" + s : s;
}

Date.prototype.format = function (fmt) {
  var o = {
    "M+": this.getMonth() + 1, //月份
    "d+": this.getDate(), //日
    "h+": this.getHours(), //小时
    "m+": this.getMinutes(), //分
    "s+": this.getSeconds(), //秒
    "q+": Math.floor((this.getMonth() + 3) / 3), //季度
    S: this.getMilliseconds(), //毫秒
  };
  if (/(y+)/.test(fmt)) {
    fmt = fmt.replace(
      RegExp.$1,
      (this.getFullYear() + "").substr(4 - RegExp.$1.length)
    );
  }
  for (var k in o) {
    if (new RegExp("(" + k + ")").test(fmt)) {
      fmt = fmt.replace(
        RegExp.$1,
        RegExp.$1.length == 1 ? o[k] : ("00" + o[k]).substr(("" + o[k]).length)
      );
    }
  }
  return fmt;
};

/* 获得实时指数列表行情 */
function getListData(code) {
  $.ajax({
    type: "GET",
    dataType: "jsonp",
    url: hq_queryUrl + "/v1/sh1/list/self/" + code,
    jsonp: "callback",
    data: {
      select: "code,name,last,chg_rate,amount,open,prev_close",
    },
    cache: false,
    success: function (resultData) {
      $(".hqMain_data .new_date").html(
        "更新时间：" + dateFormat(resultData.date + "" + resultData.time)
      );
      for (var i = 0; i < resultData.list.length; i++) {
        var data = resultData.list[i];
        var chg_rate = data[3];
        var upordown = "",
          tab_big_upordown = "",
          tab_small_upordown = "",
          common_style = "";
        if (data[6] != data[2]) {
          if (chg_rate.toFixed(2) > 0) {
            chg_rate = "+" + chg_rate.toFixed(2);
            upordown = "trending-up";
            tab_big_upordown = "up_active";
            tab_small_upordown = "up_bg";
            common_style = "";
          } else {
            chg_rate = chg_rate.toFixed(2);
            upordown = "trending-down";
            tab_big_upordown = "down_active";
            tab_small_upordown = "down_bg";
            common_style = "";
          }
        } else {
          chg_rate = chg_rate.toFixed(2);
          upordown = "";
          tab_big_upordown = "";
          tab_small_upordown = "";
          common_style = "common_style";
        }
        var indexDom = $('[index="' + data[0] + '"]');
        if (common_style) {
          indexDom.addClass(common_style);
        } else {
          indexDom.removeClass("common_style");
        }
        if (indexDom.hasClass("hq_tab_active")) {
          indexDom
            .removeClass("up_active down_active up_bg down_bg")
            .addClass(tab_big_upordown);
        } else {
          indexDom
            .removeClass("up_active down_active up_bg down_bg")
            .addClass(tab_small_upordown);
        }
        indexDom
          .find(".tab1 i:last-child")
          .html(chg_rate + "%")
          .removeClass("trending-up trending-down")
          .addClass(upordown);
        indexDom
          .find(".tab2 i:first-child")
          .html(data[2])
          .removeClass("trending-up trending-down")
          .addClass(upordown);
        indexDom
          .find(".tab2 i:last-child")
          .html((data[4] / 100000000).toFixed(0) + "<small>亿元</small>")
          .removeClass("trending-up trending-down");
      }
    },
    error: function (err) {
      console.log(err);
    },
  });
}

/* 获取当日指数、股票、基金、债券行情走势值 */
function drawOneDayChart(code, area, date, isFirst, _type, isBond) {
  var linedata = [],
    avgdata = [],
    volume = [],
    volmax = [],
    dateseries = [],
    high = 0,
    low = 0,
    prev_close = 0,
    highlist = [],
    lowlist = [],
    name = "";
  var obj = {};
  if (date == "" || date == null || date == undefined) {
    $.ajax({
      type: "GET",
      dataType: "jsonp",
      url: hq_queryUrl + (isBond ? hqBondUrl : hqOthUrl) + "snap/" + code,
      jsonp: "callback",
      data: {
        select: "prev_close,name",
      },
      cache: false,
      success: function (resultData) {
        prev_close = resultData.snap[0];
        name = resultData.snap[1];
        obj["prev_close"] = prev_close;
        obj["name"] = name;
        $.ajax({
          type: "GET",
          dataType: "jsonp",
          url: hq_queryUrl + (isBond ? hqBondUrl : hqOthUrl) + "line/" + code,
          jsonp: "callback",
          data: {
            select: "time,price,volume,avg_price,amount,highest,lowest",
          },
          cache: false,
          success: function (res) {
            for (var i = 0; i < res.line.length; i++) {
              var linedate = res.date * 1000000 + res.line[i][0];
              linedata.push([
                convertDateToUTC(String(linedate)),
                res.line[i][1],
              ]);
              avgdata.push([
                convertDateToUTC(String(linedate)),
                res.line[i][3],
              ]);
              volume.push([convertDateToUTC(String(linedate)), res.line[i][2]]);
              volmax.push(res.line[i][2]);
            }
            obj["linedata"] = linedata;
            obj["avgdata"] = avgdata;
            obj["volume"] = volume;
            obj["volmax"] = volmax;
            dateseries.push(String(res.date));
            obj["dateseries"] = dateseries;
            high = res.highest;
            low = res.lowest;
            yPositions1 = [
              parseInt(
                (prev_close -
                  Math.max(
                    Math.abs(high - prev_close),
                    Math.abs(prev_close - low)
                  )) *
                1000
              ) / 1000,
              parseInt(
                (prev_close -
                  Math.max(
                    Math.abs(high - prev_close),
                    Math.abs(prev_close - low)
                  ) /
                  2) *
                1000
              ) / 1000,
              prev_close,
              parseInt(
                (prev_close +
                  Math.max(
                    Math.abs(high - prev_close),
                    Math.abs(prev_close - low)
                  ) /
                  2) *
                1000
              ) / 1000,
              parseInt(
                (prev_close +
                  Math.max(
                    Math.abs(high - prev_close),
                    Math.abs(prev_close - low)
                  )) *
                1000
              ) / 1000,
            ];
            yPositions2 = [
              (((prev_close -
                    Math.max(
                      Math.abs(high - prev_close),
                      Math.abs(prev_close - low)
                    )) /
                  prev_close -
                  1) *
                10000) /
              100,
              (((prev_close -
                    Math.max(
                      Math.abs(high - prev_close),
                      Math.abs(prev_close - low)
                    ) /
                    2) /
                  prev_close -
                  1) *
                10000) /
              100,
              "0.00",
              (((prev_close +
                    Math.max(
                      Math.abs(high - prev_close),
                      Math.abs(prev_close - low)
                    ) /
                    2) /
                  prev_close -
                  1) *
                10000) /
              100,
              (((prev_close +
                    Math.max(
                      Math.abs(high - prev_close),
                      Math.abs(prev_close - low)
                    )) /
                  prev_close -
                  1) *
                10000) /
              100,
            ];
            yPositions3 = [
              0,
              Math.max.apply(null, obj["volmax"]) * 0.5,
              Math.max.apply(null, obj["volmax"]),
            ];
            obj["yPositions1"] = yPositions1;
            obj["yPositions2"] = yPositions2;
            obj["yPositions3"] = yPositions3;
            if (isFirst == true) {
              if (["astock", "kcbstock", "gbf", "cpf", "cbf", "etf"].includes(_type)) {
                createOneYSDayChart(area, obj, _type);
              } else if (_type == "index") {
                getJSONP({
                  url: sseQueryURL + "sseQuery/commonSoaQuery.do?jsonCallBack=?",
                  data: {
                    indexCode: code,
                    sqlId: "DB_ZSJBXX",
                    isPagination: true,
                    "pageHelp.pageSize": 25,
                    "pageHelp.pageCount": 50,
                    "pageHelp.pageNo": 1,
                    "pageHelp.beginPage": 1,
                    "pageHelp.cacheSize": 1,
                    "pageHelp.endPage": 5,
                  },
                  successCallback: function (data) {
                    var results = data.result;
                    if (
                      !extendedIsEmpty(results) &&
                      results[0].closeBatch == "2"
                    ) {
                      createOneYSDayChart(area, obj, _type);
                    } else {
                      createOneDayChart(area, obj, _type);
                    }
                  },
                  errCallback: function (err) {
                    createOneDayChart(area, obj, _type);
                  },
                });
              } else {
                createOneDayChart(area, obj, _type);
              }
            } else {
              updateOneDayChart(obj);
            }
          },
          error: function (err) {
            console.log(err);
          },
        });
      },
      error: function (err) {
        console.log(err);
      },
    });
  } else {
    $.ajax({
      type: "GET",
      dataType: "jsonp",
      url: hq_queryUrl + (isBond ? hqBondUrl : hqOthUrl) + "mink/" + code,
      jsonp: "callback",
      data: {
        select: "date,close,volume,high,low,prevClose,avg",
        begin: 0,
        end: -1,
        period: date,
      },
      cache: false,
      success: function (res) {
        if (res.kline.length != 0) {
          obj["name"] = res.code;
          prevClose = res.kline[0][5];
          obj["prev_close"] = prevClose;
          for (var i = 0; i < res.kline.length; i++) {
            linedata.push([
              convertDateToUTC(String(res.kline[i][0])),
              res.kline[i][1],
            ]); //主要线数据
            volume.push([
              convertDateToUTC(String(res.kline[i][0])),
              res.kline[i][2],
            ]); //成交量
            volmax.push(res.kline[i][2]); // 最大成交量
            highlist.push(res.kline[i][3]); // 最高值
            lowlist.push(res.kline[i][4]); //最低值
          }
          obj["linedata"] = linedata;
          obj["volume"] = volume;
          obj["volmax"] = volmax;
          dateseries.push(String(res.kline[0][0]).slice(0, 8));
          obj["dateseries"] = dateseries;

          high = Math.max.apply(null, highlist);
          low = Math.min.apply(null, lowlist);
          var yPositions1 = [
            parseInt(
              (prevClose -
                Math.max(
                  Math.abs(high - prevClose),
                  Math.abs(prevClose - low)
                )) *
              1000
            ) / 1000,
            parseInt(
              (prevClose -
                Math.max(
                  Math.abs(high - prevClose),
                  Math.abs(prevClose - low)
                ) /
                2) *
              1000
            ) / 1000,
            prevClose,
            parseInt(
              (prevClose +
                Math.max(
                  Math.abs(high - prevClose),
                  Math.abs(prevClose - low)
                ) /
                2) *
              1000
            ) / 1000,
            parseInt(
              (prevClose +
                Math.max(
                  Math.abs(high - prevClose),
                  Math.abs(prevClose - low)
                )) *
              1000
            ) / 1000,
          ];
          var yPositions2 = [
            (((prevClose -
                  Math.max(Math.abs(high - prevClose), Math.abs(prevClose - low))) /
                prevClose -
                1) *
              10000) /
            100,
            (((prevClose -
                  Math.max(Math.abs(high - prevClose), Math.abs(prevClose - low)) /
                  2) /
                prevClose -
                1) *
              10000) /
            100,
            "0.00",
            (((prevClose +
                  Math.max(Math.abs(high - prevClose), Math.abs(prevClose - low)) /
                  2) /
                prevClose -
                1) *
              10000) /
            100,
            (((prevClose +
                  Math.max(Math.abs(high - prevClose), Math.abs(prevClose - low))) /
                prevClose -
                1) *
              10000) /
            100,
          ];
          var yPositions3 = [
            0,
            Math.max.apply(null, obj["volmax"]) * 0.5,
            Math.max.apply(null, obj["volmax"]),
          ];
          obj["yPositions1"] = yPositions1;
          obj["yPositions2"] = yPositions2;
          obj["yPositions3"] = yPositions3;
          if (isFirst == true) {
            createOneDayChart(area, obj, _type, date);
          } else {
            updateOneDayChart(obj);
          }
        } else {
          $("#market_ticker").html("<div>暂无数据</div>");
        }
      },
      error: function (err) {
        console.log(err);
      },
    });
  }
}

var oneDayChart;
/* 绘制当日指数（非延时到15:00）、主板B股、LOF、REITs、债券（非延时到15:00）行情图 start */
function createOneDayChart(area, obj, _type, date) {
  var areaWidth = $("#" + area).width();
  Highcharts.setOptions({
    lang: {
      weekdays: [
        "星期日",
        "星期一",
        "星期二",
        "星期三",
        "星期四",
        "星期五",
        "星期六",
      ],
    },
  });
  oneDayChart = Highcharts.stockChart(area, {
    chart: {
      backgroundColor: "",
      margin: [10, 2, 25, 2],
      events: {
        load: function (e) {},
      },
    },
    colors: [
      "#2c7be5",
      "#0d233a",
      "#8bbc21",
      "#910000",
      "#1aadce",
      "#492970",
      "#f28f43",
      "#77a1e5",
      "#c42525",
      "#a6c96a",
    ],
    title: {
      text: null,
    },
    legend: {
      enabled: false,
    },
    tooltip: {
      valueDecinale: 2,
      shared: true,
      useHTML: true,
      formatter: function () {
        var _name = obj["name"];
        var _date = Highcharts.dateFormat("%m月%d日", this.x);
        if (date) {
          var _week = convertWeek(
            new Date(
              date.slice(0, 4),
              date.slice(4, 6) - 1,
              date.slice(6, 8)
            ).getDay()
          );
        } else {
          var _week = Highcharts.dateFormat("%A", this.x);
        }
        var _time = Highcharts.dateFormat("%H:%M", this.x);
        if (["bstock", "etf", "lof", "fund", "gbf", "cpf", "cbf", "bond"].includes(_type)) {
          var _y = this.points[0].y.toFixed(3);
        } else {
          // 债券（最新、最高、昨收、涨跌、最低）限制三位小数位
          var _y = this.points[0].y;
        }
        if (_type == "astock" || _type == "bstock") {
          var _yy = (this.points[1].y / 100).toFixed(0);
        } else {
          var _yy = this.points[1].y;
        }
        $(".highcharts-tooltip .highcharts-label-box").attr(
          "stroke",
          this.points[0].color + ""
        );
        return (
          '<p style="margin:0px;padding:0px;font-size:14px;"><span>' +
          _name +
          '   </span><span style="' +
          Comparative(_y, obj["prev_close"]) +
          ';">' +
          _y +
          '</span></p><p style="margin:0px;padding:0px;font-size:14px;"><span>' +
          "成交量：  </span>" +
          " <span>" +
          _yy +
          '</span></p><p style="margin:0px;padding:0px;color:#999">' +
          _date +
          " " +
          _week +
          " " +
          _time +
          "</p>"
        );
      },
    },
    rangeSelector: {
      enabled: false,
    },
    navigator: {
      enabled: false,
    },
    scrollbar: {
      enabled: false,
    },
    xAxis: {
      tickLength: 0,
      startOnTick: true,
      endOnTick: true,
      crosshair: {
        enabled: true,
        color: "rgba(45,38,27,.4)",
      },
      breaks: [{
        /* 中午时间 */
        from: Date.UTC(2011, 9, 6, 11, 30),
        to: Date.UTC(2011, 9, 6, 13),
        repeat: 24 * 36e5,
        breakSize: 1,
      }, ],
      gridLineColor: "rgba(224,224,224)",
      gridLineDashStyle: "ShortDash",
      gridLineWidth: 1,
      labels: {
        style: {
          "font-size": "12px",
        },
        useHTML: true,
        step: 1,
        formatter: function () {
          var returnTime = Highcharts.dateFormat("%H:%M", this.value);
          if (returnTime == "11:30") {
            return "<span >11:30/13:00</span>";
          } else if (returnTime == "09:30") {
            return '<span  style="margin-left:32px;">09:30</span>';
          } else if (returnTime == "15:00") {
            return '<span  style="margin-left:-32px;">15:00</span>';
          } else {
            return returnTime;
          }
        },
      },
      /* 以yesterdayClose为界限，统一间隔值，从 最小到最大步进 */
      tickPositioner: function () {
        var positions = [];
        if (areaWidth > 600) {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 100000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 110000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 133000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 143000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 150000))
            );
          }
        } else {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 150000))
            );
          }
        }

        return positions;
      },
    },
    credits: {
      enabled: false,
    },
    yAxis: [{
        opposite: false,
        minPadding: 0,
        showFirstLabel: true,
        showLastLabel: true,
        offset: 0,
        crosshair: {
          enabled: true,
          color: "rgba(45,38,27,.4)",
        },
        labels: {
          align: "left",
          x: 2,
          y: 0,
          style: {
            color: "#231e18",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            if (["bstock", "etf", "lof", "fund", "gbf", "cpf", "cbf", "bond"].includes(_type)) {
              var yValue = (this.value * 1).toFixed(3);
            } else {
              var yValue = (this.value * 1).toFixed(2);
            }

            return (
              '<span style="position:relative;top:3px;" class=' +
              Comparative(this.value, obj["prev_close"]) +
              ">" +
              yValue +
              "</span>"
            );
          },
        },
        height: "70%",
        gridLineColor: "rgba(45,38,27,.1)",
        lineColor: "rgba(45,38,27,.1)",
        gridLineWidth: 1,
        gridLineDashStyle: "ShortDash",
        tickPositions: obj["yPositions1"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
      {
        opposite: true, //是否把它显示到另一边（右边）
        showFirstLabel: true,
        showLastLabel: true,
        minPadding: 0,
        offset: 0,
        labels: {
          align: "right",
          x: 0,
          y: 5,
          style: {
            color: "rgba(102,102,102)",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            /* 主图右侧轴描述 */
            return (
              '<span style="position:relative;top:-2px;font-size:12px" class=' +
              Comparative(this.value, 0) +
              ">" +
              Math.abs(this.value * 1).toFixed(2) +
              "%</span>"
            );
          },
        },
        height: "70%",
        lineWidth: 0,
        gridLineWidth: 0,
        tickPositions: obj["yPositions2"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
      {
        labels: {
          align: "right",
          x: -3,
          y: 0,
          style: {
            color: "rgba(102,102,102)",
            fontSize: "12",
          },
        },
        tickPositions: obj["yPositions3"],
        showLastLabel: false,
        showFirstLabel: false,
        top: "78%",
        height: "22%",
        offset: 0,
        lineWidth: 0,
        gridLineColor: "rgba(224,224,224)",
        gridLineWidth: 1,
        gridLineDashStyle: "ShortDash",
        opposite: false,
      },
    ],
    series: [{
        data: obj["linedata"],
        type: "area",
        color: "#dc3545",
        shadow: true,
        dataGrouping: {
          enabled: false,
        },
        lineWidth: 1,
        threshold: obj["prev_close"],
        negativeColor: "#28a745",
        negativeFillColor: {
          lineWidth: 1,
          linearGradient: {
            //渐变方向
            x1: 0,
            y1: 1,
            x2: 0,
            y2: 0,
          },
          shadow: true,
          stops: [
            [0, Highcharts.Color("#28a745").setOpacity(0.2).get("rgba")],
            [1, Highcharts.Color("#28a745").setOpacity(0).get("rgba")],
          ],
        },
        fillColor: {
          lineWidth: 1,
          linearGradient: {
            //渐变方向
            x1: 0,
            y1: 0,
            x2: 0,
            y2: 1,
          },
          shadow: true,
          stops: [
            [0, Highcharts.Color("#dc3545").setOpacity(0.2).get("rgba")],
            [1, Highcharts.Color("#dc3545").setOpacity(0).get("rgba")],
          ],
        },
        zIndex: 40,
        id: "sz1",
      },
      {
        type: "column",
        data: obj["volume"],
        linkedTo: "sz1",
        color: "#887C77",
        yAxis: 2,
        dataGrouping: {
          enabled: false,
        },
        borderRadius: 2,
        pointPadding: 0.25,
        pointWidth: 1,
        id: "sz2",
        zIndex: 40,
      },
    ],
  });
}
/* 绘制当日指数（非延时到15:00）、主板B股、LOF、REITs、债券（非延时到15:00）行情图 end */

/* 绘制当日指数（延时到15:30）、主板A股、科创板股票、债券（延时到15：30）、ETF行情图 start */
function createOneYSDayChart(area, obj, _type, date) {
  var areaWidth = $("#" + area).width();
  Highcharts.setOptions({
    lang: {
      weekdays: [
        "星期日",
        "星期一",
        "星期二",
        "星期三",
        "星期四",
        "星期五",
        "星期六",
      ],
    },
  });
  oneDayChart = Highcharts.stockChart(area, {
    chart: {
      backgroundColor: "",
      margin: [10, 2, 25, 2],
      events: {
        load: function (e) {},
      },
    },
    colors: [
      "#2c7be5",
      "#0d233a",
      "#8bbc21",
      "#910000",
      "#1aadce",
      "#492970",
      "#f28f43",
      "#77a1e5",
      "#c42525",
      "#a6c96a",
    ],
    title: {
      text: null,
    },
    legend: {
      enabled: false,
    },
    tooltip: {
      valueDecinale: 2,
      shared: true,
      useHTML: true,
      formatter: function () {
        var _name = obj["name"];
        var _date = Highcharts.dateFormat("%m月%d日", this.x);
        if (date) {
          var _week = convertWeek(
            new Date(
              date.slice(0, 4),
              date.slice(4, 6) - 1,
              date.slice(6, 8)
            ).getDay()
          );
        } else {
          var _week = Highcharts.dateFormat("%A", this.x);
        }
        var _time = Highcharts.dateFormat("%H:%M", this.x);
        if (["bstock", "etf", "lof", "fund", "gbf", "cpf", "cbf", "bond"].includes(_type)) {
          var _y = this.points[0].y.toFixed(3);
        } else {
          var _y = this.points[0].y;
        }
        if (_type == "astock") {
          var _yy = (this.points[1].y / 100).toFixed(0);
        } else {
          var _yy = this.points[1].y;
        }
        $(".highcharts-tooltip .highcharts-label-box").attr(
          "stroke",
          this.points[0].color + ""
        );
        return (
          '<p style="margin:0px;padding:0px;font-size:14px;"><span>' +
          _name +
          '   </span><span style="' +
          Comparative(_y, obj["prev_close"]) +
          ';">' +
          _y +
          '</span></p><p style="margin:0px;padding:0px;font-size:14px;"><span>' +
          "成交量：  </span>" +
          " <span>" +
          _yy +
          '</span></p><p style="margin:0px;padding:0px;color:#999">' +
          _date +
          " " +
          _week +
          " " +
          _time +
          "</p>"
        );
      },
    },
    rangeSelector: {
      enabled: false,
    },
    navigator: {
      enabled: false,
    },
    scrollbar: {
      enabled: false,
    },
    xAxis: {
      tickLength: 0,
      startOnTick: true,
      endOnTick: true,
      crosshair: {
        enabled: true,
        color: "rgba(45,38,27,.4)",
      },
      breaks: [{
        /* 中午时间 */
        from: Date.UTC(2011, 9, 6, 11, 30),
        to: Date.UTC(2011, 9, 6, 13),
        repeat: 24 * 36e5,
        breakSize: 1,
      }, ],
      gridLineColor: "rgba(224,224,224)",
      gridLineDashStyle: "ShortDash",
      gridLineWidth: 1,
      labels: {
        style: {
          "font-size": "12px",
        },
        useHTML: true,
        step: 1,
        formatter: function () {
          var returnTime = Highcharts.dateFormat("%H:%M", this.value);
          if (returnTime == "11:30") {
            return "<span >11:30/13:00</span>";
          } else if (returnTime == "09:30") {
            return '<span  style="margin-left:32px;">09:30</span>';
          } else if (returnTime == "15:00") {
            return '<span  style="margin-left:-32px;">15:00</span>';
          } else if (returnTime == "15:30") {
            return '<span  style="margin-left:-32px;">15:30</span>';
          } else {
            return returnTime;
          }
        },
      },
      /* 以yesterdayClose为界限，统一间隔值，从 最小到最大步进 */
      tickPositioner: function () {
        var positions = [];
        if (areaWidth > 600) {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 100000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 110000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 133000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 143000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 150000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 153000))
            );
          }
        } else {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 153000))
            );
          }
        }

        return positions;
      },
    },
    credits: {
      enabled: false,
    },
    yAxis: [{
        opposite: false,
        minPadding: 0,
        showFirstLabel: true,
        showLastLabel: true,
        offset: 0,
        crosshair: {
          enabled: true,
          color: "rgba(45,38,27,.4)",
        },
        labels: {
          align: "left",
          x: 2,
          y: 0,
          style: {
            color: "#231e18",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            // 债券调整为三位小数
            if (["bstock", "etf", "lof", "fund", "gbf", "cpf", "cbf", "bond"].includes(_type)) {
              var yValue = (this.value * 1).toFixed(3);
            } else {
              var yValue = (this.value * 1).toFixed(2);
            }
            return (
              '<span style="position:relative;top:3px;" class=' +
              Comparative(this.value, obj["prev_close"]) +
              ">" +
              yValue +
              "</span>"
            );
          },
        },
        height: "70%",
        gridLineColor: "rgba(45,38,27,.1)",
        lineColor: "rgba(45,38,27,.1)",
        gridLineWidth: 1,
        gridLineDashStyle: "ShortDash",
        tickPositions: obj["yPositions1"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
      {
        opposite: true, //是否把它显示到另一边（右边）
        showFirstLabel: true,
        showLastLabel: true,
        minPadding: 0,
        offset: 0,
        labels: {
          align: "right",
          x: 0,
          y: 5,
          style: {
            color: "rgba(102,102,102)",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            /* 主图右侧轴描述 */
            return (
              '<span style="position:relative;top:-2px;font-size:12px" class=' +
              Comparative(this.value, 0) +
              ">" +
              Math.abs(this.value * 1).toFixed(2) +
              "%</span>"
            );
          },
        },
        height: "70%",
        lineWidth: 0,
        gridLineWidth: 0,
        tickPositions: obj["yPositions2"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
      {
        labels: {
          align: "right",
          x: -3,
          y: 0,
          style: {
            color: "rgba(102,102,102)",
            fontSize: "12",
          },
        },
        tickPositions: obj["yPositions3"],
        showLastLabel: false,
        showFirstLabel: false,
        top: "78%",
        height: "22%",
        offset: 0,
        lineWidth: 0,
        gridLineColor: "rgba(224,224,224)",
        gridLineWidth: 1,
        gridLineDashStyle: "ShortDash",
        opposite: false,
      },
    ],
    series: [{
        data: obj["linedata"],
        type: "area",
        color: "#dc3545",
        shadow: true,
        dataGrouping: {
          enabled: false,
        },
        lineWidth: 1,
        threshold: obj["prev_close"],
        negativeColor: "#28a745",
        negativeFillColor: {
          lineWidth: 1,
          linearGradient: {
            //渐变方向
            x1: 0,
            y1: 1,
            x2: 0,
            y2: 0,
          },
          shadow: true,
          stops: [
            [0, Highcharts.Color("#28a745").setOpacity(0.2).get("rgba")],
            [1, Highcharts.Color("#28a745").setOpacity(0).get("rgba")],
          ],
        },
        fillColor: {
          lineWidth: 1,
          linearGradient: {
            //渐变方向
            x1: 0,
            y1: 0,
            x2: 0,
            y2: 1,
          },
          shadow: true,
          stops: [
            [0, Highcharts.Color("#dc3545").setOpacity(0.2).get("rgba")],
            [1, Highcharts.Color("#dc3545").setOpacity(0).get("rgba")],
          ],
        },
        zIndex: 40,
        id: "sz1",
      },
      {
        type: "column",
        data: obj["volume"],
        linkedTo: "sz1",
        color: "#887C77",
        yAxis: 2,
        dataGrouping: {
          enabled: false,
        },
        borderRadius: 2,
        pointPadding: 0.25,
        pointWidth: 1,
        id: "sz2",
        zIndex: 40,
      },
    ],
  });
}
/* 绘制当日指数（延时到15:30）、主板A股、科创板股票、债券（延时到15：30）、ETF行情图 end */

/* 行情图更新数据重绘 */
function updateOneDayChart(obj) {
  oneDayChart.yAxis[0].update({
    tickPositions: obj["yPositions1"],
    redraw: false,
  });
  oneDayChart.yAxis[1].update({
    tickPositions: obj["yPositions2"],
    redraw: false,
  });
  oneDayChart.yAxis[2].update({
    tickPositions: obj["yPositions3"],
    redraw: false,
  });
  var sz1 = oneDayChart.get("sz1");
  sz1.setData(obj["linedata"], true, false, false);
  var sz2 = oneDayChart.get("sz2");
  sz2.setData(obj["volume"], true, false, false);
  oneDayChart.redraw();
}

/* 获取当日指数、主板、基金、债券行情走势值(无成交量) - 检索页和绿色证券首页*/
function drawOneSmallZChart(code, area, isFirst, id, isShowExtendname) {
  var linedata = [],
    volume = [],
    volmax = [],
    dateseries = [],
    high = 0,
    low = 0,
    prev_close = 0,
    name = "";
  var obj = {};
  getJSONP({
    url: sseQueryURL + "commonQuery.do?jsonCallBack=?",
    data: {
      isPagination: false, //是否分页
      sqlId: "COMMON_SSE_ZQLX_C",
      SEC_CODE: code,
    },
    successCallback: function (data) {
      var isBond = "";
      if (data && data.result && data.result.length > 0) {
        var SEC_TYPE = data.result[0].SEC_TYPE;
        var SUB_TYPE = data.result[0].SUB_TYPE;
        obj.allBondType = {
          describe: "债券类型",
          SEC_TYPE: SEC_TYPE,
          SUB_TYPE: SUB_TYPE,
        };
        if (
          SEC_TYPE == "D" &&
          SUB_TYPE != "DST" &&
          SUB_TYPE != "DVP" &&
          SUB_TYPE != "TCB" &&
          SUB_TYPE != "WIT"
        ) {
          isBond = true;
        } else {
          isBond = false;
        }
      } else {
        isBond = false;
        obj.allBondType = {
          describe: "债券类型",
          SEC_TYPE: "index",
          SUB_TYPE: "index",
        };
      }
      $.ajax({
        type: "GET",
        dataType: "jsonp",
        url: hq_queryUrl + (isBond ? hqBondUrl : hqOthUrl) + "snap/" + code,
        jsonp: "callback",
        data: {
          select: "prev_close,name,cpxxextendname",
        },
        cache: false,
        success: function (resultData) {
          prev_close = resultData.snap[0];
          if(isShowExtendname){
            //基金显示扩位简称
            name = resultData.snap[2];
          }else{
            name = resultData.snap[1];
          }
          obj["name"] = name;
          obj["prev_close"] = prev_close;
          $.ajax({
            type: "GET",
            dataType: "jsonp",
            url: hq_queryUrl + (isBond ? hqBondUrl : hqOthUrl) + "line/" + code,
            jsonp: "callback",
            data: {
              select: "time,price,volume,avg_price,amount,highest,lowest",
            },
            cache: false,
            success: function (res) {
              if (res.line.length == 0 && id) {
                $(id).empty();
                $(id).append(
                  '<div class="d-flex align-items-center justify-content-center noChart_message">暂无走势信息</div>'
                );
                return;
              }
              for (var i = 0; i < res.line.length; i++) {
                var linedate = res.date * 1000000 + res.line[i][0];
                linedata.push([
                  convertDateToUTC(String(linedate)),
                  res.line[i][1],
                ]);
                volume.push([
                  convertDateToUTC(String(linedate)),
                  res.line[i][2],
                ]);
                volmax.push(res.line[i][2]);
              }
              obj["linedata"] = linedata;
              obj["volume"] = volume;
              obj["volmax"] = volmax;
              dateseries.push(String(res.date));
              obj["dateseries"] = dateseries;
              high = res.highest;
              low = res.lowest;
              yPositions1 = [
                parseInt(
                  (prev_close -
                    Math.max(
                      Math.abs(high - prev_close),
                      Math.abs(prev_close - low)
                    )) *
                  1000
                ) / 1000,
                parseInt(
                  (prev_close -
                    Math.max(
                      Math.abs(high - prev_close),
                      Math.abs(prev_close - low)
                    ) /
                    2) *
                  1000
                ) / 1000,
                prev_close,
                parseInt(
                  (prev_close +
                    Math.max(
                      Math.abs(high - prev_close),
                      Math.abs(prev_close - low)
                    ) /
                    2) *
                  1000
                ) / 1000,
                parseInt(
                  (prev_close +
                    Math.max(
                      Math.abs(high - prev_close),
                      Math.abs(prev_close - low)
                    )) *
                  1000
                ) / 1000,
              ];
              yPositions2 = [
                (((prev_close -
                      Math.max(
                        Math.abs(high - prev_close),
                        Math.abs(prev_close - low)
                      )) /
                    prev_close -
                    1) *
                  10000) /
                100,
                (((prev_close -
                      Math.max(
                        Math.abs(high - prev_close),
                        Math.abs(prev_close - low)
                      ) /
                      2) /
                    prev_close -
                    1) *
                  10000) /
                100,
                "0.00",
                (((prev_close +
                      Math.max(
                        Math.abs(high - prev_close),
                        Math.abs(prev_close - low)
                      ) /
                      2) /
                    prev_close -
                    1) *
                  10000) /
                100,
                (((prev_close +
                      Math.max(
                        Math.abs(high - prev_close),
                        Math.abs(prev_close - low)
                      )) /
                    prev_close -
                    1) *
                  10000) /
                100,
              ];
              yPositions3 = [
                0,
                Math.max.apply(null, obj["volmax"]) * 0.5,
                Math.max.apply(null, obj["volmax"]),
              ];
              obj["yPositions1"] = yPositions1;
              obj["yPositions2"] = yPositions2;
              obj["yPositions3"] = yPositions3;
              if (isFirst == true) {
                var results = data.result;
                if (extendedIsEmpty(results)) {
                  getJSONP({
                    url: sseQueryURL + "sseQuery/commonSoaQuery.do?jsonCallBack=?",
                    data: {
                      indexCode: code,
                      sqlId: "DB_ZSJBXX",
                      isPagination: true,
                      "pageHelp.pageSize": 25,
                      "pageHelp.pageCount": 50,
                      "pageHelp.pageNo": 1,
                      "pageHelp.beginPage": 1,
                      "pageHelp.cacheSize": 1,
                      "pageHelp.endPage": 5,
                    },
                    successCallback: function (data) {
                      var results = data.result;
                      if (
                        !extendedIsEmpty(results) &&
                        results[0].closeBatch == "2"
                      ) {
                        createOneSmallZYSChart(area, obj);
                      } else {
                        createOneSmallZChart(area, obj);
                      }
                    },
                    errCallback: function (err) {
                      createOneSmallZChart(area, obj);
                    },
                  });
                } else if (["GBF", "CPF", "CBF", "ASH", "KSH", "EBS"].includes(results[0].SUB_TYPE)) {
                  createOneSmallZYSChart(area, obj);
                } else {
                  createOneSmallZChart(area, obj);
                }
              } else {
                updateOneSmallZChart(obj);
              }
            },
            error: function (err) {
              console.log(err);
              $(id).empty();
              $(id).append(
                '<div class="d-flex align-items-center justify-content-center noChart_message">暂无走势信息</div>'
              );
            },
          });
        },
        error: function (err) {
          console.log(err);
          $(id).empty();
          $(id).append(
            '<div class="d-flex align-items-center justify-content-center noChart_message">暂无走势信息</div>'
          );
        },
      });
    },
    errCallback: function (err) {
      console.log(err);
      $(id).empty();
      $(id).append(
        '<div class="d-flex align-items-center justify-content-center noChart_message">暂无走势信息</div>'
      );
    },
  });
}
/* 绘制当日指数、主板、基金、债券无成交量行情图 start 延长至15：30*/
var oneSmallZYSChart;

function createOneSmallZYSChart(area, obj) {
  var areaWidth = $("#" + area).width();
  var isConform = obj.allBondType.SEC_TYPE == "D" || obj.allBondType.SEC_TYPE == "EU" || obj.allBondType.SEC_TYPE == "CB";
  oneSmallZYSChart = Highcharts.stockChart(area, {
    chart: {
      backgroundColor: "",
      margin: [10, 2, 25, 2],
      events: {
        load: function (e) {},
      },
    },
    colors: [
      "#2c7be5",
      "#0d233a",
      "#8bbc21",
      "#910000",
      "#1aadce",
      "#492970",
      "#f28f43",
      "#77a1e5",
      "#c42525",
      "#a6c96a",
    ],
    title: {
      text: null,
    },
    legend: {
      enabled: false,
    },
    tooltip: {
      valueDecinale: 2,
      shared: true,
      useHTML: true,
      formatter: function () {
        var _name = obj["name"];
        var _date = Highcharts.dateFormat("%m月%d日", this.x);
        var _week = convertWeek(Highcharts.dateFormat("%A", this.x));
        var _time = Highcharts.dateFormat("%H:%M", this.x);
        var _y = this.points[0].y;
        if (isConform) {
          _y = this.points[0].y.toFixed(3);
        }
        $(".highcharts-tooltip .highcharts-label-box").attr(
          "stroke",
          this.points[0].color + ""
        );
        return (
          '<p style="margin:0px;padding:0px;font-size:14px;"><span>' +
          _name +
          '   </span><span style="' +
          Comparative(_y, obj["prev_close"]) +
          ';">' +
          _y +
          '</span></p><p style="margin:0px;padding:0px;color:#999">' +
          _date +
          " " +
          _week +
          " " +
          _time +
          "</p>"
        );
      },
    },
    rangeSelector: {
      enabled: false,
    },
    navigator: {
      enabled: false,
    },
    scrollbar: {
      enabled: false,
    },
    xAxis: {
      tickLength: 0,
      startOnTick: true,
      endOnTick: true,
      crosshair: {
        enabled: true,
        color: "rgba(45,38,27,.4)",
      },
      breaks: [{
        /* 中午时间 */
        from: Date.UTC(2011, 9, 6, 11, 30),
        to: Date.UTC(2011, 9, 6, 13),
        repeat: 24 * 36e5,
        breakSize: 1,
      }, ],
      gridLineColor: "rgba(224,224,224)",
      gridLineDashStyle: "ShortDash",
      gridLineWidth: 1,
      labels: {
        style: {
          "font-size": "12px",
        },
        useHTML: true,
        step: 1,
        formatter: function () {
          var returnTime = Highcharts.dateFormat("%H:%M", this.value);
          if (returnTime == "11:30") {
            return "<span >11:30/13:00</span>";
          } else if (returnTime == "09:30") {
            return '<span  style="margin-left:32px;">09:30</span>';
          } else if (returnTime == "15:00") {
            return '<span  style="margin-left:-32px;">15:00</span>';
          } else if (returnTime == "15:30") {
            return '<span  style="margin-left:-32px;">15:30</span>';
          } else {
            return returnTime;
          }
        },
      },
      /* 以yesterdayClose为界限，统一间隔值，从 最小到最大步进 */
      tickPositioner: function () {
        var positions = [];
        if (areaWidth > 600) {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 100000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 110000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 133000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 143000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 150000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 153000))
            );
          }
        } else {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 150000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 153000))
            );
          }
        }

        return positions;
      },
    },
    credits: {
      enabled: false,
    },
    yAxis: [{
        opposite: false,
        minPadding: 0,
        showFirstLabel: true,
        showLastLabel: true,
        offset: 0,
        crosshair: {
          enabled: true,
          color: "rgba(45,38,27,.4)",
        },
        labels: {
          align: "left",
          x: 2,
          y: 0,
          style: {
            color: "#231e18",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            return (
              '<span style="position:relative;top:3px;">' +
              (isConform ?
                (this.value * 1).toFixed(3) :
                (this.value * 1).toFixed(2)) +
              "</span>"
            );
          },
        },
        height: "100%",
        gridLineColor: "rgba(45,38,27,.1)",
        lineColor: "rgba(45,38,27,.1)",
        gridLineWidth: 1,
        gridLineDashStyle: "ShortDash",
        tickPositions: obj["yPositions1"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
      {
        opposite: true, //是否把它显示到另一边（右边）
        showFirstLabel: true,
        showLastLabel: true,
        minPadding: 0,
        offset: 0,
        labels: {
          align: "right",
          x: 0,
          y: 5,
          style: {
            color: "rgba(102,102,102)",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            /* 主图右侧轴描述 */
            return (
              '<span style="position:relative;top:-2px;font-size:12px;" class=' +
              Comparative(this.value, 0) +
              ">" +
              Math.abs(this.value * 1).toFixed(2) +
              "%</span>"
            );
          },
        },
        height: "100%",
        lineWidth: 0,
        gridLineWidth: 0,
        tickPositions: obj["yPositions2"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
    ],
    series: [{
      data: obj["linedata"],
      type: "area",
      color: "#dc3545",
      shadow: true,
      dataGrouping: {
        enabled: false,
      },
      lineWidth: 1,
      threshold: obj["prev_close"],
      negativeColor: "#28a745",
      negativeFillColor: {
        lineWidth: 1,
        linearGradient: {
          //渐变方向
          x1: 0,
          y1: 1,
          x2: 0,
          y2: 0,
        },
        shadow: true,
        stops: [
          [0, Highcharts.Color("#28a745").setOpacity(0.2).get("rgba")],
          [1, Highcharts.Color("#28a745").setOpacity(0).get("rgba")],
        ],
      },
      fillColor: {
        lineWidth: 1,
        linearGradient: {
          //渐变方向
          x1: 0,
          y1: 0,
          x2: 0,
          y2: 1,
        },
        shadow: true,
        stops: [
          [0, Highcharts.Color("#dc3545").setOpacity(0.2).get("rgba")],
          [1, Highcharts.Color("#dc3545").setOpacity(0).get("rgba")],
        ],
      },
      zIndex: 40,
      id: "sz1",
    }, ],
  });
}

/* 绘制当日指数、主板、基金、债券无成交量行情图 start */
var oneSmallZChart;

function createOneSmallZChart(area, obj) {
  var areaWidth = $("#" + area).width();
  var isConform = obj.allBondType.SEC_TYPE == "D" || obj.allBondType.SEC_TYPE == "EU" || obj.allBondType.SEC_TYPE == "CB";
  oneSmallZChart = Highcharts.stockChart(area, {
    chart: {
      backgroundColor: "",
      margin: [10, 2, 25, 2],
      events: {
        load: function (e) {},
      },
    },
    colors: [
      "#2c7be5",
      "#0d233a",
      "#8bbc21",
      "#910000",
      "#1aadce",
      "#492970",
      "#f28f43",
      "#77a1e5",
      "#c42525",
      "#a6c96a",
    ],
    title: {
      text: null,
    },
    legend: {
      enabled: false,
    },
    tooltip: {
      valueDecinale: 2,
      shared: true,
      useHTML: true,
      formatter: function () {
        var _name = obj["name"];
        var _date = Highcharts.dateFormat("%m月%d日", this.x);
        var _week = convertWeek(Highcharts.dateFormat("%A", this.x));
        var _time = Highcharts.dateFormat("%H:%M", this.x);
        var _y = this.points[0].y;
        if (isConform) {
          _y = this.points[0].y.toFixed(3);
        }
        $(".highcharts-tooltip .highcharts-label-box").attr(
          "stroke",
          this.points[0].color + ""
        );
        return (
          '<p style="margin:0px;padding:0px;font-size:14px;"><span>' +
          _name +
          '   </span><span style="' +
          Comparative(_y, obj["prev_close"]) +
          ';">' +
          _y +
          '</span></p><p style="margin:0px;padding:0px;color:#999">' +
          _date +
          " " +
          _week +
          " " +
          _time +
          "</p>"
        );
      },
    },
    rangeSelector: {
      enabled: false,
    },
    navigator: {
      enabled: false,
    },
    scrollbar: {
      enabled: false,
    },
    xAxis: {
      tickLength: 0,
      startOnTick: true,
      endOnTick: true,
      crosshair: {
        enabled: true,
        color: "rgba(45,38,27,.4)",
      },
      breaks: [{
        /* 中午时间 */
        from: Date.UTC(2011, 9, 6, 11, 30),
        to: Date.UTC(2011, 9, 6, 13),
        repeat: 24 * 36e5,
        breakSize: 1,
      }, ],
      gridLineColor: "rgba(224,224,224)",
      gridLineDashStyle: "ShortDash",
      gridLineWidth: 1,
      labels: {
        style: {
          "font-size": "12px",
        },
        useHTML: true,
        step: 1,
        formatter: function () {
          var returnTime = Highcharts.dateFormat("%H:%M", this.value);
          if (returnTime == "11:30") {
            return "<span >11:30/13:00</span>";
          } else if (returnTime == "09:30") {
            return '<span  style="margin-left:32px;">09:30</span>';
          } else if (returnTime == "15:00") {
            return '<span  style="margin-left:-32px;">15:00</span>';
          } else {
            return returnTime;
          }
        },
      },
      /* 以yesterdayClose为界限，统一间隔值，从 最小到最大步进 */
      tickPositioner: function () {
        var positions = [];
        if (areaWidth > 600) {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 100000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 110000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 133000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 143000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 150000))
            );
          }
        } else {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 150000))
            );
          }
        }

        return positions;
      },
    },
    credits: {
      enabled: false,
    },
    yAxis: [{
        opposite: false,
        minPadding: 0,
        showFirstLabel: true,
        showLastLabel: true,
        offset: 0,
        crosshair: {
          enabled: true,
          color: "rgba(45,38,27,.4)",
        },
        labels: {
          align: "left",
          x: 2,
          y: 0,
          style: {
            color: "#231e18",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            return (
              '<span style="position:relative;top:3px;">' +
              (isConform ?
                (this.value * 1).toFixed(3) :
                (this.value * 1).toFixed(2)) +
              "</span>"
            );
          },
        },
        height: "100%",
        gridLineColor: "rgba(45,38,27,.1)",
        lineColor: "rgba(45,38,27,.1)",
        gridLineWidth: 1,
        gridLineDashStyle: "ShortDash",
        tickPositions: obj["yPositions1"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
      {
        opposite: true, //是否把它显示到另一边（右边）
        showFirstLabel: true,
        showLastLabel: true,
        minPadding: 0,
        offset: 0,
        labels: {
          align: "right",
          x: 0,
          y: 5,
          style: {
            color: "rgba(102,102,102)",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            /* 主图右侧轴描述 */
            return (
              '<span style="position:relative;top:-2px;font-size:12px;" class=' +
              Comparative(this.value, 0) +
              ">" +
              Math.abs(this.value * 1).toFixed(2) +
              "%</span>"
            );
          },
        },
        height: "100%",
        lineWidth: 0,
        gridLineWidth: 0,
        tickPositions: obj["yPositions2"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
    ],
    series: [{
      data: obj["linedata"],
      type: "area",
      color: "#dc3545",
      shadow: true,
      dataGrouping: {
        enabled: false,
      },
      lineWidth: 1,
      threshold: obj["prev_close"],
      negativeColor: "#28a745",
      negativeFillColor: {
        lineWidth: 1,
        linearGradient: {
          //渐变方向
          x1: 0,
          y1: 1,
          x2: 0,
          y2: 0,
        },
        shadow: true,
        stops: [
          [0, Highcharts.Color("#28a745").setOpacity(0.2).get("rgba")],
          [1, Highcharts.Color("#28a745").setOpacity(0).get("rgba")],
        ],
      },
      fillColor: {
        lineWidth: 1,
        linearGradient: {
          //渐变方向
          x1: 0,
          y1: 0,
          x2: 0,
          y2: 1,
        },
        shadow: true,
        stops: [
          [0, Highcharts.Color("#dc3545").setOpacity(0.2).get("rgba")],
          [1, Highcharts.Color("#dc3545").setOpacity(0).get("rgba")],
        ],
      },
      zIndex: 40,
      id: "sz1",
    }, ],
  });
}

/* 行情图更新数据重绘 */
function updateOneSmallZChart(obj) {
  oneSmallZChart.yAxis[0].update({
    tickPositions: obj["yPositions1"],
    redraw: false,
  });
  oneSmallZChart.yAxis[1].update({
    tickPositions: obj["yPositions2"],
    redraw: false,
  });
  var sz1 = oneSmallZChart.get("sz1");
  sz1.setData(obj["linedata"], true, false, false);
  oneSmallZChart.redraw();
}
/* 绘制当日指数、主板、基金、债券无成交量行情图 end */

/* 获取当日回购行情走势值 */
function drawOneDayHGChart(code, area, date, isFirst, isBond) {
  var linedata = [],
    avgdata = [],
    volume = [],
    volmax = [],
    dateseries = [],
    high = 0,
    low = 0,
    prev_close = 0,
    highlist = [],
    lowlist = [];
  name = "";
  var obj = {};
  if (date == "" || date == null || date == undefined) {
    $.ajax({
      type: "GET",
      dataType: "jsonp",
      url: hq_queryUrl + "v1/shb1/snap/" + code,
      jsonp: "callback",
      data: {
        select: "prev_close,name",
      },
      cache: false,
      success: function (resultData) {
        prev_close = resultData.snap[0];
        name = resultData.snap[1];
        obj["prev_close"] = prev_close;
        obj["name"] = name;
        $.ajax({
          type: "GET",
          dataType: "jsonp",
          url: hq_queryUrl + "v1/shb1/line/" + code,
          jsonp: "callback",
          data: {
            select: "time,price,volume,avg_price,amount",
          },
          cache: false,
          success: function (res) {
            var line = res.line;
            if (line.length > 0) {
              $(".hgjj").html(line[line.length - 1][3]);
            }
            for (var i = 0; i < res.line.length; i++) {
              var linedate = res.date * 1000000 + res.line[i][0];
              linedata.push([
                convertDateToUTC(String(linedate)),
                res.line[i][1],
              ]);
              avgdata.push([
                convertDateToUTC(String(linedate)),
                res.line[i][3],
              ]);
              volume.push([convertDateToUTC(String(linedate)), res.line[i][2]]);
              volmax.push(res.line[i][2]);
            }
            obj["linedata"] = linedata;
            obj["avgdata"] = avgdata;
            obj["volume"] = volume;
            obj["volmax"] = volmax;
            dateseries.push(String(res.date));
            obj["dateseries"] = dateseries;
            high = res.highest;
            low = res.lowest;
            yPositions1 = [
              parseInt(
                (prev_close -
                  Math.max(
                    Math.abs(high - prev_close),
                    Math.abs(prev_close - low)
                  )) *
                1000
              ) / 1000,
              parseInt(
                (prev_close -
                  Math.max(
                    Math.abs(high - prev_close),
                    Math.abs(prev_close - low)
                  ) /
                  2) *
                1000
              ) / 1000,
              prev_close,
              parseInt(
                (prev_close +
                  Math.max(
                    Math.abs(high - prev_close),
                    Math.abs(prev_close - low)
                  ) /
                  2) *
                1000
              ) / 1000,
              parseInt(
                (prev_close +
                  Math.max(
                    Math.abs(high - prev_close),
                    Math.abs(prev_close - low)
                  )) *
                1000
              ) / 1000,
            ];
            yPositions2 = [
              prev_close -
              Math.max(
                Math.abs(high - prev_close),
                Math.abs(prev_close - low)
              ) -
              prev_close,
              prev_close -
              Math.max(
                Math.abs(high - prev_close),
                Math.abs(prev_close - low)
              ) /
              2 -
              prev_close,
              "0.000",
              prev_close -
              (prev_close -
                Math.max(
                  Math.abs(high - prev_close),
                  Math.abs(prev_close - low)
                ) /
                2),
              prev_close -
              (prev_close -
                Math.max(
                  Math.abs(high - prev_close),
                  Math.abs(prev_close - low)
                )),
            ];
            yPositions3 = [
              0,
              Math.max.apply(null, obj["volmax"]) * 0.5,
              Math.max.apply(null, obj["volmax"]),
            ];
            obj["yPositions1"] = yPositions1;
            obj["yPositions2"] = yPositions2;
            obj["yPositions3"] = yPositions3;
            if (isFirst == true) {
              createOneDayHGChart(area, obj);
            } else {
              updateOneDayHGChart(obj);
            }
          },
          error: function (err) {
            console.log(err);
          },
        });
      },
      error: function (err) {
        console.log(err);
      },
    });
  } else {
    $.ajax({
      type: "GET",
      dataType: "jsonp",
      url: hq_queryUrl + "v1/shb1/mink/" + code,
      jsonp: "callback",
      data: {
        select: "date,close,volume,high,low,prevClose,avg",
        begin: 0,
        end: -1,
        period: date,
      },
      cache: false,
      success: function (res) {
        if (res.kline.length != 0) {
          obj["name"] = res.code;
          prevClose = res.kline[0][5];
          obj["prev_close"] = prevClose;
          for (var i = 0; i < res.kline.length; i++) {
            linedata.push([
              convertDateToUTC(String(res.kline[i][0])),
              res.kline[i][1],
            ]); //主要线数据
            avgdata.push([
              convertDateToUTC(String(res.kline[i][0])),
              res.kline[i][6],
            ]);
            volume.push([
              convertDateToUTC(String(res.kline[i][0])),
              res.kline[i][2],
            ]); //成交量
            volmax.push(res.kline[i][2]); // 最大成交量
            highlist.push(res.kline[i][3]); // 最高值
            lowlist.push(res.kline[i][4]); //最低值
          }
          obj["linedata"] = linedata;
          obj["avgdata"] = avgdata;
          obj["volume"] = volume;
          obj["volmax"] = volmax;
          dateseries.push(String(res.kline[0][0]).slice(0, 8));
          obj["dateseries"] = dateseries;

          high = Math.max.apply(null, highlist);
          low = Math.min.apply(null, lowlist);
          var yPositions1 = [
            parseInt(
              (prevClose -
                Math.max(
                  Math.abs(high - prevClose),
                  Math.abs(prevClose - low)
                )) *
              1000
            ) / 1000,
            parseInt(
              (prevClose -
                Math.max(
                  Math.abs(high - prevClose),
                  Math.abs(prevClose - low)
                ) /
                2) *
              1000
            ) / 1000,
            prevClose,
            parseInt(
              (prevClose +
                Math.max(
                  Math.abs(high - prevClose),
                  Math.abs(prevClose - low)
                ) /
                2) *
              1000
            ) / 1000,
            parseInt(
              (prevClose +
                Math.max(
                  Math.abs(high - prevClose),
                  Math.abs(prevClose - low)
                )) *
              1000
            ) / 1000,
          ];
          var yPositions2 = [
            parseInt(
              ((prevClose -
                  Math.max(
                    Math.abs(high - prevClose),
                    Math.abs(prevClose - low)
                  )) /
                prevClose -
                1) *
              10000
            ) / 100,
            parseInt(
              ((prevClose -
                  Math.max(
                    Math.abs(high - prevClose),
                    Math.abs(prevClose - low)
                  ) /
                  2) /
                prevClose -
                1) *
              10000
            ) / 100,
            "0.00",
            parseInt(
              ((prevClose +
                  Math.max(
                    Math.abs(high - prevClose),
                    Math.abs(prevClose - low)
                  ) /
                  2) /
                prevClose -
                1) *
              10000
            ) / 100,
            parseInt(
              ((prevClose +
                  Math.max(
                    Math.abs(high - prevClose),
                    Math.abs(prevClose - low)
                  )) /
                prevClose -
                1) *
              10000
            ) / 100,
          ];
          var yPositions3 = [
            0,
            Math.max.apply(null, obj["volmax"]) * 0.5,
            Math.max.apply(null, obj["volmax"]),
          ];
          obj["yPositions1"] = yPositions1;
          obj["yPositions2"] = yPositions2;
          obj["yPositions3"] = yPositions3;
          if (isFirst == true) {
            createOneDayHGChart(area, obj, date);
          } else {
            updateOneDayHGChart(obj);
          }
        } else {
          $("#market_ticker").html("<div>暂无数据</div>");
        }
      },
      error: function (err) {
        console.log(err);
      },
    });
  }
}

/* 获取当日回购行情走势值（无成交量）-全文检索 */
function drawOneSmallHGChart(code, area, isFirst, isBond) {
  var linedata = [],
    avgdata = [],
    dateseries = [],
    high = 0,
    low = 0,
    prev_close = 0,
    name = "";
  var obj = {};
  $.ajax({
    type: "GET",
    dataType: "jsonp",
    url: hq_queryUrl + "v1/shb1/snap/" + code,
    jsonp: "callback",
    data: {
      select: "prev_close,name",
    },
    cache: false,
    success: function (resultData) {
      prev_close = resultData.snap[0];
      name = resultData.snap[1];
      obj["prev_close"] = prev_close;
      obj["name"] = name;
      $.ajax({
        type: "GET",
        dataType: "jsonp",
        url: hq_queryUrl + "v1/shb1/line/" + code,
        jsonp: "callback",
        data: {
          select: "time,price,volume,avg_price",
        },
        cache: false,
        success: function (res) {
          var line = res.line;
          if (line.length > 0) {
            $(".hgjj").html(line[line.length - 1][3]);
          }
          for (var i = 0; i < res.line.length; i++) {
            var linedate = res.date * 1000000 + res.line[i][0];
            linedata.push([convertDateToUTC(String(linedate)), res.line[i][1]]);
            avgdata.push([convertDateToUTC(String(linedate)), res.line[i][3]]);
          }
          obj["linedata"] = linedata;
          obj["avgdata"] = avgdata;
          dateseries.push(String(res.date));
          obj["dateseries"] = dateseries;
          high = res.highest;
          low = res.lowest;
          yPositions1 = [
            parseInt(
              (prev_close -
                Math.max(
                  Math.abs(high - prev_close),
                  Math.abs(prev_close - low)
                )) *
              1000
            ) / 1000,
            parseInt(
              (prev_close -
                Math.max(
                  Math.abs(high - prev_close),
                  Math.abs(prev_close - low)
                ) /
                2) *
              1000
            ) / 1000,
            prev_close,
            parseInt(
              (prev_close +
                Math.max(
                  Math.abs(high - prev_close),
                  Math.abs(prev_close - low)
                ) /
                2) *
              1000
            ) / 1000,
            parseInt(
              (prev_close +
                Math.max(
                  Math.abs(high - prev_close),
                  Math.abs(prev_close - low)
                )) *
              1000
            ) / 1000,
          ];
          yPositions2 = [
            prev_close -
            Math.max(
              Math.abs(high - prev_close),
              Math.abs(prev_close - low)
            ) -
            prev_close,
            prev_close -
            Math.max(
              Math.abs(high - prev_close),
              Math.abs(prev_close - low)
            ) /
            2 -
            prev_close,
            "0.000",
            prev_close -
            (prev_close -
              Math.max(
                Math.abs(high - prev_close),
                Math.abs(prev_close - low)
              ) /
              2),
            prev_close -
            (prev_close -
              Math.max(
                Math.abs(high - prev_close),
                Math.abs(prev_close - low)
              )),
          ];
          obj["yPositions1"] = yPositions1;
          obj["yPositions2"] = yPositions2;
          if (isFirst == true) {
            createOneSmallHGChart(area, obj);
          } else {
            updateOneSmallHGChart(obj);
          }
        },
        error: function (err) {
          console.log(err);
          var id = $("#" + area);
          $(id).empty();
          $(id).append(
            '<div class="d-flex align-items-center justify-content-center noChart_message">暂无走势信息</div>'
          );
        },
      });
    },
    error: function (err) {
      console.log(err);
      var id = $("#" + area);
      $(id).empty();
      $(id).append(
        '<div class="d-flex align-items-center justify-content-center noChart_message">暂无走势信息</div>'
      );
    },
  });
}

/* 绘制当日回购行情图 start */
var oneSmallHGChart;

function createOneSmallHGChart(area, obj, date) {
  var areaWidth = $("#" + area).width();
  Highcharts.setOptions({
    lang: {
      weekdays: [
        "星期日",
        "星期一",
        "星期二",
        "星期三",
        "星期四",
        "星期五",
        "星期六",
      ],
    },
  });
  oneSmallHGChart = Highcharts.stockChart(area, {
    chart: {
      backgroundColor: "",
      margin: [10, 2, 25, 2],
      events: {
        load: function (e) {},
      },
    },
    colors: [
      "#2c7be5",
      "#0d233a",
      "#8bbc21",
      "#910000",
      "#1aadce",
      "#492970",
      "#f28f43",
      "#77a1e5",
      "#c42525",
      "#a6c96a",
    ],
    title: {
      text: null,
    },
    legend: {
      enabled: false,
    },
    tooltip: {
      valueDecinale: 2,
      shared: true,
      useHTML: true,
      formatter: function () {
        var _name = obj["name"];
        var _date = Highcharts.dateFormat("%m月%d日", this.x);
        var _week = Highcharts.dateFormat("%A", this.x);
        var _time = Highcharts.dateFormat("%H:%M", this.x);
        var _y = this.points[0].y.toFixed(3);
        var _avg = this.points[1].y.toFixed(3);
        $(".highcharts-tooltip .highcharts-label-box").attr(
          "stroke",
          this.points[0].color + ""
        );
        return (
          '<p style="margin:0px;padding:0px;font-size:14px;">' +
          "<span>" +
          _name +
          "  " +
          '</span><span style="' +
          Comparative(_y, obj["prev_close"]) +
          ';">' +
          _y +
          "</span></p>" +
          '<p style="margin:0px;padding:0px;font-size:14px;">' +
          "<span>均价：  </span>" +
          " <span>" +
          _avg +
          "</span></p>" +
          '<p style="margin:0px;padding:0px;font-size:14px;">' +
          '<p style="margin:0px;padding:0px;color:#999">' +
          _date +
          " " +
          _week +
          " " +
          _time +
          "</p>"
        );
      },
    },
    rangeSelector: {
      enabled: false,
    },
    navigator: {
      enabled: false,
    },
    scrollbar: {
      enabled: false,
    },
    xAxis: {
      tickLength: 0,
      startOnTick: true,
      endOnTick: true,
      crosshair: {
        enabled: true,
        color: "rgba(45,38,27,.4)",
      },
      breaks: [{
        /* 中午时间 */
        from: Date.UTC(2011, 9, 6, 11, 30),
        to: Date.UTC(2011, 9, 6, 13),
        repeat: 24 * 36e5,
        breakSize: 1,
      }, ],
      gridLineColor: "rgba(224,224,224)",
      gridLineDashStyle: "ShortDash",
      gridLineWidth: 1,
      labels: {
        style: {
          "font-size": "12px",
        },
        useHTML: true,
        step: 1,
        formatter: function () {
          var returnTime = Highcharts.dateFormat("%H:%M", this.value);
          if (returnTime == "11:30") {
            return "<span >11:30/13:00</span>";
          } else if (returnTime == "09:30") {
            return '<span  style="margin-left:32px;">09:30</span>';
          } else if (returnTime == "15:00") {
            return '<span  style="margin-left:-32px;">15:00</span>';
          } else if (returnTime == "15:30") {
            return '<span  style="margin-left:-32px;">15:30</span>';
          } else {
            return returnTime;
          }
        },
      },
      /* 以yesterdayClose为界限，统一间隔值，从 最小到最大步进 */
      tickPositioner: function () {
        var positions = [];
        if (areaWidth > 600) {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 100000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 110000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 133000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 143000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 150000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 153000))
            );
          }
        } else {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 153000))
            );
          }
        }

        return positions;
      },
    },
    credits: {
      enabled: false,
    },
    yAxis: [{
        opposite: false,
        minPadding: 0,
        showFirstLabel: true,
        showLastLabel: true,
        offset: 0,
        crosshair: {
          enabled: true,
          color: "rgba(45,38,27,.4)",
        },
        labels: {
          align: "left",
          x: 2,
          y: 0,
          style: {
            color: "#231e18",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            return (
              '<span style="position:relative;top:3px;" class=' +
              Comparative(this.value, obj["prev_close"]) +
              ">" +
              (this.value * 1).toFixed(3) +
              "</span>"
            );
          },
        },
        height: "100%",
        gridLineColor: "rgba(45,38,27,.1)",
        lineColor: "rgba(45,38,27,.1)",
        gridLineWidth: 1,
        gridLineDashStyle: "ShortDash",
        tickPositions: obj["yPositions1"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
      {
        opposite: true, //是否把它显示到另一边（右边）
        showFirstLabel: true,
        showLastLabel: true,
        minPadding: 0,
        offset: 0,
        labels: {
          align: "right",
          x: 0,
          y: 5,
          style: {
            color: "rgba(102,102,102)",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            /* 主图右侧轴描述 */
            return (
              '<span style="position:relative;top:3px;" class=' +
              Comparative(this.value, 0) +
              ">" +
              Math.abs(this.value * 1).toFixed(3) +
              "</span>"
            );
          },
        },
        height: "100%",
        lineWidth: 0,
        gridLineWidth: 0,
        tickPositions: obj["yPositions2"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
    ],
    series: [{
        data: obj["linedata"],
        type: "area",
        color: "#dc3545",
        shadow: true,
        dataGrouping: {
          enabled: false,
        },
        lineWidth: 1,
        threshold: obj["prev_close"],
        negativeColor: "#28a745",
        negativeFillColor: {
          lineWidth: 1,
          linearGradient: {
            //渐变方向
            x1: 0,
            y1: 1,
            x2: 0,
            y2: 0,
          },
          shadow: true,
          stops: [
            [0, Highcharts.Color("#28a745").setOpacity(0.2).get("rgba")],
            [1, Highcharts.Color("#28a745").setOpacity(0).get("rgba")],
          ],
        },
        fillColor: {
          lineWidth: 1,
          linearGradient: {
            //渐变方向
            x1: 0,
            y1: 0,
            x2: 0,
            y2: 1,
          },
          shadow: true,
          stops: [
            [0, Highcharts.Color("#dc3545").setOpacity(0.2).get("rgba")],
            [1, Highcharts.Color("#dc3545").setOpacity(0).get("rgba")],
          ],
        },
        zIndex: 40,
        id: "sz1",
      },
      {
        type: "line",
        data: obj["avgdata"],
        yAxis: 0,
        color: "rgb(52, 109, 164)",
        marker: {
          symbol: "circle",
        },
        dataGrouping: {
          enabled: false,
        },
        id: "sz2",
        zIndex: 40,
      },
    ],
  });
}

/* 行情图更新数据重绘 */
function updateOneSmallHGChart(obj) {
  oneSmallHGChart.yAxis[0].update({
    tickPositions: obj["yPositions1"],
    redraw: false,
  });
  oneSmallHGChart.yAxis[1].update({
    tickPositions: obj["yPositions2"],
    redraw: false,
  });
  var sz1 = oneSmallHGChart.get("sz1");
  sz1.setData(obj["linedata"], true, false, false);
  var sz3 = oneSmallHGChart.get("sz2");
  sz3.setData(obj["avgdata"], true, false, false);
  oneDayHGChart.redraw();
}

/* 绘制当日回购行情图 end */

/* 绘制当日回购行情图 start */
var oneDayHGChart;

function createOneDayHGChart(area, obj, date) {
  var areaWidth = $("#" + area).width();
  Highcharts.setOptions({
    lang: {
      weekdays: [
        "星期日",
        "星期一",
        "星期二",
        "星期三",
        "星期四",
        "星期五",
        "星期六",
      ],
    },
  });
  oneDayHGChart = Highcharts.stockChart(area, {
    chart: {
      backgroundColor: "",
      margin: [10, 2, 25, 2],
      events: {
        load: function (e) {},
      },
    },
    colors: [
      "#2c7be5",
      "#0d233a",
      "#8bbc21",
      "#910000",
      "#1aadce",
      "#492970",
      "#f28f43",
      "#77a1e5",
      "#c42525",
      "#a6c96a",
    ],
    title: {
      text: null,
    },
    legend: {
      enabled: false,
    },
    tooltip: {
      valueDecinale: 2,
      shared: true,
      useHTML: true,
      formatter: function () {
        var _name = obj["name"];
        var _date = Highcharts.dateFormat("%m月%d日", this.x);
        if (date) {
          var _week = convertWeek(
            new Date(
              date.slice(0, 4),
              date.slice(4, 6) - 1,
              date.slice(6, 8)
            ).getDay()
          );
        } else {
          var _week = Highcharts.dateFormat("%A", this.x);
        }
        var _time = Highcharts.dateFormat("%H:%M", this.x);
        var _y = this.points[0].y.toFixed(3);
        var _avg = this.points[1].y.toFixed(3);
        var _volume = this.points[2].y;
        $(".highcharts-tooltip .highcharts-label-box").attr(
          "stroke",
          this.points[0].color + ""
        );
        return (
          '<p style="margin:0px;padding:0px;font-size:14px;">' +
          "<span>" +
          _name +
          "  " +
          '</span><span style="' +
          Comparative(_y, obj["prev_close"]) +
          ';">' +
          _y +
          "</span></p>" +
          '<p style="margin:0px;padding:0px;font-size:14px;">' +
          "<span>均价：  </span>" +
          " <span>" +
          _avg +
          "</span></p>" +
          '<p style="margin:0px;padding:0px;font-size:14px;">' +
          "<span>成交量：  </span>" +
          " <span>" +
          _volume +
          "</span></p>" +
          '<p style="margin:0px;padding:0px;color:#999">' +
          _date +
          " " +
          _week +
          " " +
          _time +
          "</p>"
        );
      },
    },
    rangeSelector: {
      enabled: false,
    },
    navigator: {
      enabled: false,
    },
    scrollbar: {
      enabled: false,
    },
    xAxis: {
      tickLength: 0,
      startOnTick: true,
      endOnTick: true,
      crosshair: {
        enabled: true,
        color: "rgba(45,38,27,.4)",
      },
      breaks: [{
        /* 中午时间 */
        from: Date.UTC(2011, 9, 6, 11, 30),
        to: Date.UTC(2011, 9, 6, 13),
        repeat: 24 * 36e5,
        breakSize: 1,
      }, ],
      gridLineColor: "rgba(224,224,224)",
      gridLineDashStyle: "ShortDash",
      gridLineWidth: 1,
      labels: {
        style: {
          "font-size": "12px",
        },
        useHTML: true,
        step: 1,
        formatter: function () {
          var returnTime = Highcharts.dateFormat("%H:%M", this.value);
          if (returnTime == "11:30") {
            return "<span >11:30/13:00</span>";
          } else if (returnTime == "09:30") {
            return '<span  style="margin-left:32px;">09:30</span>';
          } else if (returnTime == "15:00") {
            return '<span  style="margin-left:-32px;">15:00</span>';
          } else if (returnTime == "15:30") {
            return '<span  style="margin-left:-32px;">15:30</span>';
          } else {
            return returnTime;
          }
        },
      },
      /* 以yesterdayClose为界限，统一间隔值，从 最小到最大步进 */
      tickPositioner: function () {
        var positions = [];
        if (areaWidth > 600) {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 100000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 110000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 133000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 143000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 150000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 153000))
            );
          }
        } else {
          for (var i = 0; i < obj["dateseries"].length; i++) {
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 93000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 103000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 113000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 140000))
            );
            positions.push(
              convertDateToUTC(String(obj["dateseries"][i] * 1000000 + 153000))
            );
          }
        }

        return positions;
      },
    },
    credits: {
      enabled: false,
    },
    yAxis: [{
        opposite: false,
        minPadding: 0,
        showFirstLabel: true,
        showLastLabel: true,
        offset: 0,
        crosshair: {
          enabled: true,
          color: "rgba(45,38,27,.4)",
        },
        labels: {
          align: "left",
          x: 2,
          y: 0,
          style: {
            color: "#231e18",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            return (
              '<span style="position:relative;top:3px;" class=' +
              Comparative(this.value, obj["prev_close"]) +
              ">" +
              (this.value * 1).toFixed(3) +
              "</span>"
            );
          },
        },
        height: "70%",
        gridLineColor: "rgba(45,38,27,.1)",
        lineColor: "rgba(45,38,27,.1)",
        gridLineWidth: 1,
        gridLineDashStyle: "ShortDash",
        tickPositions: obj["yPositions1"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
      {
        opposite: true, //是否把它显示到另一边（右边）
        showFirstLabel: true,
        showLastLabel: true,
        minPadding: 0,
        offset: 0,
        labels: {
          align: "right",
          x: 0,
          y: 5,
          style: {
            color: "rgba(102,102,102)",
            fontSize: "12",
          },
          useHTML: true,
          formatter: function () {
            /* 主图右侧轴描述 */
            return (
              '<span style="position:relative;top:3px;" class=' +
              Comparative(this.value, 0) +
              ">" +
              Math.abs(this.value * 1).toFixed(3) +
              "</span>"
            );
          },
        },
        height: "70%",
        lineWidth: 0,
        gridLineWidth: 0,
        tickPositions: obj["yPositions2"], //以yesterdayClose为界限，统一间隔值，从 最小到最大步进
      },
      {
        labels: {
          align: "right",
          x: -3,
          y: 0,
          style: {
            color: "rgba(102,102,102)",
            fontSize: "12",
          },
        },
        tickPositions: obj["yPositions3"],
        showLastLabel: false,
        showFirstLabel: false,
        top: "78%",
        height: "22%",
        offset: 0,
        lineWidth: 0,
        gridLineColor: "rgba(224,224,224)",
        gridLineWidth: 1,
        gridLineDashStyle: "ShortDash",
        opposite: false,
      },
    ],
    series: [{
        data: obj["linedata"],
        type: "area",
        color: "#dc3545",
        shadow: true,
        dataGrouping: {
          enabled: false,
        },
        lineWidth: 1,
        threshold: obj["prev_close"],
        negativeColor: "#28a745",
        negativeFillColor: {
          lineWidth: 1,
          linearGradient: {
            //渐变方向
            x1: 0,
            y1: 1,
            x2: 0,
            y2: 0,
          },
          shadow: true,
          stops: [
            [0, Highcharts.Color("#28a745").setOpacity(0.2).get("rgba")],
            [1, Highcharts.Color("#28a745").setOpacity(0).get("rgba")],
          ],
        },
        fillColor: {
          lineWidth: 1,
          linearGradient: {
            //渐变方向
            x1: 0,
            y1: 0,
            x2: 0,
            y2: 1,
          },
          shadow: true,
          stops: [
            [0, Highcharts.Color("#dc3545").setOpacity(0.2).get("rgba")],
            [1, Highcharts.Color("#dc3545").setOpacity(0).get("rgba")],
          ],
        },
        zIndex: 40,
        id: "sz1",
      },
      {
        type: "line",
        data: obj["avgdata"],
        yAxis: 0,
        color: "rgb(52, 109, 164)",
        marker: {
          symbol: "circle",
        },
        dataGrouping: {
          enabled: false,
        },
        id: "sz3",
        zIndex: 40,
      },
      {
        type: "column",
        data: obj["volume"],
        linkedTo: "sz1",
        color: "#887C77",
        yAxis: 2,
        dataGrouping: {
          enabled: false,
        },
        borderRadius: 2,
        pointPadding: 0.25,
        pointWidth: 1,
        id: "sz2",
        zIndex: 40,
      },
    ],
  });
}

/* 行情图更新数据重绘 */
function updateOneDayHGChart(obj) {
  oneDayHGChart.yAxis[0].update({
    tickPositions: obj["yPositions1"],
    redraw: false,
  });
  oneDayHGChart.yAxis[1].update({
    tickPositions: obj["yPositions2"],
    redraw: false,
  });
  oneDayHGChart.yAxis[2].update({
    tickPositions: obj["yPositions3"],
    redraw: false,
  });
  var sz1 = oneDayHGChart.get("sz1");
  sz1.setData(obj["linedata"], true, false, false);
  var sz2 = oneDayHGChart.get("sz2");
  sz2.setData(obj["volume"], true, false, false);
  var sz3 = oneDayHGChart.get("sz3");
  sz3.setData(obj["avgdata"], true, false, false);
  oneDayHGChart.redraw();
}

/* 绘制当日回购行情图 end */

/* 绘制指数、主板、基金、债券K线图 start */
/* K线不关联分时走势图 */
function drawKChart(code, area, isFirst, isBond) {
  var obj = {},
    ohlc = [],
    volume = [];
  obj["code"] = code;
  $.ajax({
    type: "GET",
    dataType: "jsonp",
    url: hq_queryUrl + (isBond ? hqBondUrl : hqOthUrl) + "dayk/" + code,
    jsonp: "callback",
    data: {
      begin: -1000,
      end: -1,
      period: "day",
    },
    cache: false,
    success: function (res) {
      for (var i = 0; i < res.kline.length; i += 1) {
        ohlc.push([
          convertDateToUTC(String(res.kline[i][0])), // the date
          res.kline[i][1], // open
          res.kline[i][2], // high
          res.kline[i][3], // low
          res.kline[i][4], // close
          res.kline[i][5], // the volume
        ]);
        volume.push([
          convertDateToUTC(String(res.kline[i][0])), // the date
          res.kline[i][5], // the volume
        ]);
      }
      obj["ohlc"] = ohlc;
      obj["volume"] = volume;
      if (isFirst == true) {
        createKChart(area, "", obj, isBond);
      } else {
        updateKChart(obj);
      }
    },
    error: function (err) {
      console.log(err);
    },
  });
}

/* K线关联分时走势图 */
/* code为证券代码，kChartArea为K线绘制区域id，timeChartArea为分时绘制区域id，isFirst为是否为第一次绘图 */
function drawKTimeChart(
  code,
  type,
  kChartArea,
  timeChartArea,
  isFirst,
  isBond
) {
  var obj = {},
    ohlc = [],
    volume = [];
  obj["code"] = code;
  obj["type"] = type;
  $.ajax({
    type: "GET",
    dataType: "jsonp",
    url: hq_queryUrl + (isBond ? hqBondUrl : hqOthUrl) + "dayk/" + code,
    jsonp: "callback",
    data: {
      begin: -1000,
      end: -1,
      period: "day",
    },
    cache: false,
    success: function (res) {
      for (var i = 0; i < res.kline.length; i += 1) {
        ohlc.push([
          convertDateToUTC(String(res.kline[i][0])), // the date
          res.kline[i][1], // open
          res.kline[i][2], // high
          res.kline[i][3], // low
          res.kline[i][4], // close
          res.kline[i][5], // the volume
        ]);
        volume.push([
          convertDateToUTC(String(res.kline[i][0])), // the date
          res.kline[i][5], // the volume
        ]);
      }
      obj["ohlc"] = ohlc;
      obj["volume"] = volume;
      if (isFirst == true) {
        createKChart(kChartArea, timeChartArea, obj, isBond);
      } else {
        updateKChart(obj);
      }
    },
    error: function (err) {
      console.log(err);
    },
  });
}

var kChart,
  transformDate = "";

function createKChart(kChartArea, tChartArea, obj, isBond) {
  Highcharts.setOptions({
    lang: {
      rangeSelectorZoom: "", //不显示'zoom'文字
      weekdays: [
        "星期日",
        "星期一",
        "星期二",
        "星期三",
        "星期四",
        "星期五",
        "星期六",
      ],
    },
  });

  var codeType = ""; //判断代码类型
  fnCodetype($("#inputCode").val(), function (_codeType) {
    codeType = _codeType;
    kChart = Highcharts.stockChart(kChartArea, {
      rangeSelector: {
        //范围选择器
        buttonTheme: {
          display: "none", //时间选择按钮
        },
        inputEnabled: false, //时间输入框
        selected: 1, //默认时间展示一个月
      },
      chart: {
        marginTop: 0, //距离顶部距离
      },
      navigator: {
        //滚动条
        margin: 0, //距离顶部距离
        series: {
          //默认值
          type: "areaspline",
          color: "#4572A7",
          fillOpacity: 0.05,
          dataGrouping: {
            smoothed: true,
          },
          lineWidth: 1,
          marker: {
            enabled: false,
          },
        },
        xAxis: {
          tickWidth: 0,
          lineWidth: 0,
          gridLineColor: "#9ea7b1",
          gridLineWidth: 1,
          tickPixelInterval: 200,
          labels: {
            align: "left",
            style: {
              color: "#9ea7b1",
            },
            x: 3,
            y: -4,
          },
        },
      },
      scrollbar: {
        enabled: true,
      },
      plotOptions: {
        candlestick: {},
        column: {
          tooltip: {
            valueDecimals: 0,
          },
        },
        macd: {
          zones: [{
              value: 0,
              color: "#28a745",
            },
            {
              color: "#dc3545",
            },
          ],
        },
      },
      xAxis: {
        tickLength: 0, //刻度线长度
        crosshair: {
          //准心线
          enabled: true,
          dashStyle: "dot",
        },
        dateTimeLabelFormats: {
          second: "%H:%M:%S",
          minute: "%H:%M",
          hour: "%H:%M",
          day: "%m-%d",
          week: "%m-%d",
          month: "%y-%m",
          year: "%Y",
        },
        labels: {
          style: {
            color: "#6c757d",
            fontSize: "12",
          },
        },
      },
      tooltip: {
        split: false,
        shared: true,
        valueDecimals: 2,
        useHTML: false,
        formatter: function () {
          var _name = obj["code"];
          var _date = Highcharts.dateFormat("%Y-%m-%d", this.x);
          var _week = Highcharts.dateFormat("%A", this.x);
          var open = this.points[0].point.open;
          var high = this.points[0].point.high;
          var low = this.points[0].point.low;
          var close = this.points[0].point.close;
          var _yy = formatNum(this.points[1].y);
          // 债券（开盘、最高、最低、收盘）限制三位小数位
          if (codeType == "gbf" || codeType == "cpf" || codeType == "cbf" || codeType == "bond") {
            var tooltipHtml =
              '<span style="font-size:11px;">' +
              _date +
              " " +
              _week +
              "</span><br>" +
              '<em style="color:#28a745;">● </em><b>' +
              _name +
              "</b><br>" +
              "<span>开盘 " +
              parseFloat(open).toFixed(3) +
              "</span><br>" +
              "<span>最高 " +
              parseFloat(high).toFixed(3) +
              "</span><br>" +
              "<span>最低 " +
              parseFloat(low).toFixed(3) +
              "</span><br>" +
              "<span>收盘 " +
              parseFloat(close).toFixed(3) +
              "</span><br>" +
              '<span><em style="color:#887c77;">● </em>成交量: <b>' +
              _yy +
              "</b></span><br>";
          } else {
            var tooltipHtml =
              '<span style="font-size:11px;">' +
              _date +
              " " +
              _week +
              "</span><br>" +
              '<em style="color:#28a745;">● </em><b>' +
              _name +
              "</b><br>" +
              "<span>开盘 " +
              open +
              "</span><br>" +
              "<span>最高 " +
              high +
              "</span><br>" +
              "<span>最低 " +
              low +
              "</span><br>" +
              "<span>收盘 " +
              close +
              "</span><br>" +
              '<span><em style="color:#887c77;">● </em>成交量: <b>' +
              _yy +
              "</b></span><br>";
          }
          return tooltipHtml;
        },
        xDateFormat: "%Y-%m-%d %A",
      },
      yAxis: [{
          opposite: false, //是否将坐标轴显示与对立面
          showFirstLabel: false, //是否显示第一标签（最下面的数轴值）
          showLastLabel: false, //是否显示最后标签（最上面的数轴值）
          minPadding: 0,
          gridLineColor: "rgba(45,38,27,.1)", //网格线颜色
          lineColor: "#e9eaf4", //坐标轴轴线的颜色
          lineWidth: 1,
          labels: {
            align: "left",
            y: 0,
            x: 0,
            style: {
              color: "#6c757d",
              fontSize: "12",
            },
            formatter: function () {
              // 债券调整为三位小数
              if (codeType == "gbf" || codeType == "cpf" || codeType == "cbf" || codeType == "bond") {
                return this.value.toFixed(3);
              } else {
                return this.value.toFixed(2);
              }
            },
          },
          height: "75%",
        },
        {
          opposite: false, //是否将坐标轴显示与对立面
          showFirstLabel: false, //是否显示第一标签（最下面的数轴值）
          showLastLabel: false, //是否显示最后标签（最上面的数轴值）
          gridLineColor: "rgba(45,38,27,.1)", //网格线颜色
          lineColor: "#e9eaf4", //坐标轴轴线的颜色
          lineWidth: 1,
          labels: {
            align: "left",
            y: 0,
            x: 0,
            style: {
              color: "#6c757d",
              fontSize: "12",
            },
            formatter: function () {
              if (this.value == 0) {
                return "万股";
              } else {
                return this.value / 10000;
              }
            },
          },
          top: "77%",
          height: "23%",
          offset: 0,
        },
        {
          opposite: false, //是否将坐标轴显示与对立面
          showFirstLabel: true, //是否显示第一标签（最下面的数轴值）
          showLastLabel: true, //是否显示最后标签（最上面的数轴值）
          gridLineColor: "#e9eaf4", //网格线颜色
          lineColor: "#e9eaf4", //坐标轴轴线的颜色
          lineWidth: 1,
          labels: {
            enabled: false,
            align: "left",
            y: 0,
            style: {
              color: "#6c757d",
              fontSize: "12",
            },
            format: "{value}",
          },
          top: "100%",
          height: "0",
          offset: 0,
        },
      ],
      credits: {
        enabled: false,
      },
      series: [{
          type: "candlestick",
          animation: true,
          name: obj["code"],
          color: "#28a745", //控制走势为跌的蜡烛颜色
          lineColor: "#28a745",
          upColor: "transparent", //控制走势为涨的蜡烛颜色
          lineWidth: 1,
          upLineColor: "#dc3545",
          data: obj["ohlc"],
          dataGrouping: {
            enabled: false,
          },
          events: {
            click: function (e) {
              if (tChartArea != "") {
                if (obj["type"] == "huigou") {
                  transformDate = transformTime(e.point.x);
                  drawOneDayHGChart(
                    obj["code"],
                    tChartArea,
                    transformDate,
                    true,
                    undefined,
                    isBond
                  );
                } else {
                  transformDate = transformTime(e.point.x);
                  drawOneDayChart(
                    obj["code"],
                    tChartArea,
                    transformDate,
                    true,
                    undefined,
                    isBond
                  );
                }
              }
            },
          },
          zIndex: 10,
          id: "ohlcId",
        },
        {
          type: "column",
          animation: false,
          name: "成交量",
          data: obj["volume"],
          color: "#887C77",
          yAxis: 1,
          dataGrouping: {
            enabled: false,
          },
          pointPadding: 0.5,
          zIndex: 10,
          id: "volumeId",
        },
      ],
    });
  });
}

/* 数据更新重绘K线图 */
function updateKChart(obj) {
  var ohlcId = kChart.get("ohlcId");
  ohlcId.setData(obj["ohlc"], true, false, false);
  var volumeId = kChart.get("volumeId");
  volumeId.setData(obj["volume"], true, false, false);
  kChart.redraw();
}
/* 绘制指数、主板、基金、债券K线图 end */

/* 绘制上证月报指数走势图 start */
function drawSZYBChart(area, obj) {
  var oneMonthChart = Highcharts.stockChart(area, {
    rangeSelector: {
      enabled: false,
    },
    navigator: {
      enabled: false,
    },
    title: {
      text: obj["name"],
    },
    plotOptions: {
      series: {
        showInLegend: true,
      },
    },
    tooltip: {
      split: false,
      shared: true,
    },
    credits: {
      enabled: false,
    },
    yAxis: [{
        opposite: false,
        showFirstLabel: true,
        showLastLabel: true,
        height: "45%",
      },
      {
        opposite: true,
        showFirstLabel: true,
        showLastLabel: true,
        top: "55%",
        height: "45%",
      },
    ],
    series: [{
        type: "line",
        name: "收盘价",
        data: obj["lineData"],
        yAxis: 0,
        id: "s1",
      },
      {
        type: "column",
        name: "成交金额（亿元）",
        data: obj["amount"],
        yAxis: 1,
        id: "s2",
        linkedTo: "s1",
      },
    ],
  });
}
/* 绘制上证月报指数近一年走势图 end */
var hq_active = $("#hq_controller .hq_tab_active"),
  inds = [];

$("#hq_container .hq_index").each(function (i, obj) {
  if (hq_active.length < 1 && i == 0) {
    $(obj).addClass("hq_tab_active");
    hq_active = $(obj);
  }
  inds.push($.trim($(obj).attr("index")));
});

/* 
    判断产品类型
    调用方式eg:
    fnCodetype(000001, function(_codeType) {
    console.log(_codeType);
    }) 
    */
function fnCodetype(code, succ, isBond) {
  if (code) {
    $.ajax({
      url: sseQueryURL + "commonQuery.do?jsonCallBack=?",
      dataType: "jsonp",
      jsonp: "jsonCallBack",
      type: "GET",
      data: {
        isPagination: false, //是否分页
        sqlId: "COMMON_SSE_ZQLX_C",
        SEC_CODE: code,
      },
      success: function (resultData) {
        var results = resultData.result;
        if (results.length == 0) {
          succ("index");
          return;
        }
        var retype = "";
        var codetype = results[0].SEC_TYPE;
        var codesubtype = results[0].SUB_TYPE;
        if (codetype) {
          switch (codetype) {
            case "ES": //股票
              switch (codesubtype) {
                case "ASH": //A股
                  retype = "astock";
                  break;
                case "BSH": //B股
                  retype = "bstock";
                  break;
                case "KSH": //科创板
                  retype = "kcbstock";
                  break;
              }
              break;
            case "EU": //基金
              switch (codesubtype) {
                case "EBS": //ETF
                  retype = "etf";
                  break;
                case "LOF": //LOF
                  retype = "lof";
                  break;
                default: 
                  retype = "fund";
              }
              break;
            case "CB": //公募REITs
              retype = "reits";
              break;
            case "D": //债券
              switch (codesubtype) {
                case "CRP": //债券回购
                  retype = "huigou";
                  break;
                case "GBF": //债券延长
                  retype = "gbf";
                  break;
                case "CPF": //债券延长
                  retype = "cpf";
                  break;
                case "CBF": //债券延长
                  retype = "cbf";
                  break;
                default:
                  retype = "bond";
              }
              break;
          }
        } else {
          //指数
          retype = "index";
        }
        succ(retype);
      },
    });
  } else {
    succ(false);
  }
}

/* 	判断当前交易状态 */
function checkStatus(tradephase) {
  if (tradephase != null && tradephase != "") {
    tradephase = tradephase.replace(/\s/gi, "");
    if (tradephase != null && tradephase != "") {
      tradephase = tradephase.substr(0, 1);
      switch (tradephase) {
        case "S":
          tradephase = "开市前";
          break;
        case "C":
          tradephase = "集合竞价";
          break;
        case "D":
          tradephase = "集合竞价结束";
          break;
        case "T":
          tradephase = "连续竞价";
          break;
        case "B":
          tradephase = "午间休市";
          break;
        case "E":
          tradephase = "闭市";
          break;
        case "P":
          tradephase = "停牌";
          break;
        case "M":
          tradephase = "熔断(可恢复)";
          break;
        case "N":
          tradephase = "熔断(至闭市)";
          break;
        case "U":
          tradephase = "收盘集合竞价";
          break;
      }
    }
  }
  return tradephase;
}

/**
 * 获取日期对象，如果isUTC为true获取 日期的UTC对象，false则获取普通日期对象
 * @param date
 * @param isUTC
 * @returns
 */
function getDateUTCOrNot(date, isUTC) {
  if (!(date instanceof String)) {
    date += "";
  }
  var dArr = new Array();
  for (var hh = 0; hh < 5; hh++) {
    var numb;
    if (hh == 0) {
      numb = Number(date.slice(0, 4));
    } else {
      numb = Number(date.slice((hh - 1) * 2 + 4, hh * 2 + 4));
    }

    dArr.push(numb);
  }
  if (isUTC == false) {
    return new Date(dArr[0], dArr[1] - 1, dArr[2], dArr[3], dArr[4]);
  }
  var dateUTC = Number(
    Date.UTC(dArr[0], dArr[1] - 1, dArr[2], dArr[3], dArr[4])
  ); //得出的UTC时间

  return dateUTC;
}

/**
 * @author ltli
 * @method { kcbShowIcon } return 图标字符串
 * @params { f, t, d } f：产品状态标志字符串，t：产品子类型，d：产品上市日期
 */
function kcbShowIcon(f, t, d) {
  var str = "";
  if (f) {
    if (f.substring(7, 8) === "U") {
      if (t === "kcbstock" && Number(d) < 20250713) {
        str +=
          "<a href='javascript:void(0);' class='icon_kcb_c1' title=''></a>";
      } else if (t === "kcbstock" && Number(d) >= 20250713) {
        str +=
          "<a href='javascript:void(0);' class='icon_kcb_c' title=''></a>";
      }
    }
    if (f.substring(8, 9) === "W") {
      str +=
        "<a href='javascript:void(0);' class='icon_kcb_w' title=''></a>";
    }
    if (f.substring(4, 5) === "Y") {
      str +=
        "<a href='javascript:void(0);' class='icon_kcb_d' title=''></a>";
    }
  }
  return str;
}

/**
 * 行情走势根据产品类型添加class
 */

function marketLineIniMethod(_lineType, _isFirst, isBond) {
  var code = $("#inputCode").val();
  getJSONP({
    url: sseQueryURL + "commonQuery.do?jsonCallBack=?",
    data: {
      isPagination: false, //是否分页
      sqlId: "COMMON_SSE_ZQLX_C",
      SEC_CODE: code,
    },
    successCallback: function (data) {
      var isBond = "";
      if (data && data.result && data.result.length > 0) {
        var SEC_TYPE = data.result[0].SEC_TYPE;
        var SUB_TYPE = data.result[0].SUB_TYPE;
        if (
          SEC_TYPE == "D" &&
          SUB_TYPE != "DST" &&
          SUB_TYPE != "DVP" &&
          SUB_TYPE != "TCB" &&
          SUB_TYPE != "WIT"
        ) {
          isBond = true;
        } else {
          isBond = false;
        }
      } else {
        isBond = false;
      }
      fnCodetype(
        code,
        function (_type) {
          if (_type) {
            switch (_type) {
              case "astock": //A股
                $(".search_market_L_hq").removeClass("isKcb isJj");
                market_snapAjax(
                  $("#inputCode").val(),
                  _type,
                  _lineType,
                  _isFirst,
                  isBond
                );
                break;
              case "bstock": //B股
                $(".search_market_L_hq").removeClass("isKcb isGdr isJj");
                market_snapAjax(
                  $("#inputCode").val(),
                  _type,
                  _lineType,
                  _isFirst,
                  isBond
                );
                break;
              case "kcbstock": //科创板
                $(".search_market_L_hq").addClass("isKcb");
                $(".search_market_L_hq").removeClass("isGdr isJj");
                market_snapAjax(
                  $("#inputCode").val(),
                  _type,
                  _lineType,
                  _isFirst,
                  isBond
                );
                break;
              case "etf": 
              case "lof":  
              case "fund": //基金
                $(".search_market_L_hq").addClass("isJj");
                $(".search_market_L_hq").removeClass("isKcb isGdr");
                market_snapAjax(
                  $("#inputCode").val(),
                  _type,
                  _lineType,
                  _isFirst,
                  isBond
                );
                break;
              case "reits": //公募reits
                $(".search_market_L_hq").addClass("isJj");
                $(".search_market_L_hq").removeClass("isKcb isGdr");
                market_snapAjax(
                  $("#inputCode").val(),
                  _type,
                  _lineType,
                  _isFirst,
                  isBond
                );
                break;
              case "gbf": //债券
              case "cpf": //债券
              case "cbf": //债券
              case "bond": //债券
                $(".search_market_L_hq").removeClass("isKcb isGdr isJj");
                market_snapAjax(
                  $("#inputCode").val(),
                  _type,
                  _lineType,
                  _isFirst,
                  isBond
                );
                break;
              case "index": //指数
                $(".search_market_L_hq").removeClass("isKcb isGdr isJj");
                market_snapAjax(
                  $("#inputCode").val(),
                  _type,
                  _lineType,
                  _isFirst,
                  isBond
                );
                break;
              case "huigou": //回购
                $(".search_market_L_hq").removeClass("isKcb isGdr isJj");
                market_snapAjax(
                  $("#inputCode").val(),
                  _type,
                  _lineType,
                  _isFirst,
                  isBond
                );
                break;
            }
          }
        },
        isBond
      );
    },
    errCallback: function (err) {
      console.log(err);
    },
  });
}

/**
 *
 * 行情信息表盘展示
 */
function market_snapAjax(_codeS, _type, _lineType, _isFirst, isBond) {
  $.ajax({
    type: "POST",
    dataType: "jsonp",
    url: hq_queryUrl + (isBond ? hqBondUrl : hqOthUrl) + "snap/" + _codeS,
    jsonp: "callback",
    data: {
      select: "name,prev_close,open,high,low,last,change,chg_rate,volume,amount,cpxxlmttype,up_limit,down_limit,tradephase,bid,ask,hlt_tag,gdr_ratio,gdr_prevpx,gdr_currency,cpxxprodusta,fp_volume,fp_amount,fp_phase,cpxxextendname,listdate",
    },
    cache: false,
    success: function (resultData) {
      if ($(".search_market_L_hq .new_date").length > 0) {
        $(".search_market_L_hq .new_date").html(
          "更新时间：" + dateFormat(resultData.date + "" + resultData.time)
        );
      }
      var _code = resultData.code;
      var pad01Arr = "";
      var pad02Arr = "";
      var pad03Arr = "";
      var pad04Arr = "";
      var _snap = resultData.snap;
      var _date = resultData.date + "";
      var _dDate =
        _date.substring(0, _date.length - 4) +
        "-" +
        _date.substring(_date.length - 4, _date.length - 2) +
        "-" +
        _date.substring(_date.length - 2);
      var _timer = resultData.time + "";
      var _dTime =
        _timer.substring(0, _timer.length - 4) +
        ":" +
        _timer.substring(_timer.length - 4, _timer.length - 2);

      var _name = _snap[0]; //名称
      var _prevClose = _snap[1]; //昨收
      var _open = _snap[2]; //开盘价
      var _high = _snap[3]; //最高价
      var _low = _snap[4]; //最低价
      var _last = _snap[5]; //现价
      var _change = _snap[6]; //涨跌
      var _chgRate = _snap[7]; //涨跌幅,有问题，应该在涨跌判断以后再取两位小数
      var _volume = _snap[8]; //成交量
      var _amount = _snap[9]; //成交额
      var _cpxxlmttype = _snap[10]; //涨跌幅限制
      var _upLimit = _snap[11]; //涨停价格
      var _downLimit = _snap[12]; //跌停价格
      var _tradephase = _snap[13]; //交易时段
      var _bid = _snap[14]; //买盘五档
      var _ask = _snap[15]; //卖盘五档
      var _hltTag = _snap[16]; //沪伦通子类别标识
      var _gdrRatio = _snap[17]; //GDR转换比例
      var _gdrPrevpx = _snap[18]; //GDR昨日收盘价
      var _gdrCurrency = _snap[19]; //GDR币种
      var _cpxxprodusta = _snap[20]; //产品状态信息字段
      var _fpVolume = _snap[21]; //盘后交易量
      var _fpAmount = _snap[22]; //盘后交易额
      var _fpPhase = _snap[23]; //盘后固定价格交易产品实时阶段及标志
      var _cpxxextendname = _snap[24]; //证券产品长简称
      var _listdate = _snap[25];  //证券产品上市日期
      /* gdr相关行情指标 */
      var showGdr = "",
        showGdrratio = "",
        showGdrprevpx = "";
      if (_hltTag == "G") {
        $(".search_market_L_hq").addClass("isGdr");
        showGdr += '<a href="javascript:void(0);" class="icon_g" title=""></a>';
        if (_gdrRatio != null && _gdrRatio != "") {
          showGdrratio +=
            '<div class="digital_con"><span>GDR转换比例</span><span class="digital_num">' +
            _gdrRatio +
            "</span></div>";
        }
        showGdrprevpx +=
          '<div class="digital_con"><span>GDR转换比例</span><span class="digital_num">' +
          _gdrPrevpx +
          _gdrCurrency +
          "</span></div>";
      } else {
        $(".search_market_L_hq").removeClass("isGdr");
      }

      /* 股票相关行情指标start */
      if (_type === "astock" || _type === "kcbstock" || _type === "etf") {
        if (_cpxxlmttype == "P") {
          _upLimit = "-";
          _downLimit = "-";
        } else {
          _upLimit = _upLimit.toFixed(2);
          _downLimit = _downLimit.toFixed(2);
        }
        var _fpPhaseStatus = "";
        if (_fpPhase[0] == "I") {
          _fpPhaseStatus = "开市前";
        }
        if (_fpPhase[0] == "A") {
          _fpPhaseStatus = "集中撮合";
        }
        if (_fpPhase[0] == "H") {
          _fpPhaseStatus = "连续交易";
        }
        if (_fpPhase[0] == "D") {
          _fpPhaseStatus = "闭市";
        }
        if (_fpPhase[0] == "F") {
          _fpPhaseStatus = "停牌";
        }
      }

      var showK =
        "<a href='javascript:void(0);' class='icon_kcb_k' title=''></a>";
      var iconStr = kcbShowIcon(_cpxxprodusta, _type, _listdate);
      /* 股票相关行情指标end */

      function zhangdie(y) {
        var classe = "";
        if (y > _prevClose) {
          classe = "col_red";
        } else if (y < _prevClose) {
          classe = "col_green";
        } else {
          classe = "";
        }
        return classe;
      }

      var classes;
      if (_change > 0) {
        classes = "col_red";
      } else if (_change < 0) {
        classes = "col_green";
      } else {
        classes = "col_color";
      }

      /* 产品行情 */
      pad01Arr += "<li>";
      pad01Arr += '<div class="quotes_code">';
      pad01Arr += ' <span class="code_name">' + _code + "</span>";

      if (["etf", "lof", "fund", "reits"].includes(_type)) {
        pad01Arr += '<div class="quotes_code">' + _cpxxextendname + "</div>";
      } else if (_type == "kcbstock") {
        pad01Arr +=
          ' <div class="code_txt">' + _name + kcbShowIconFlag(_cpxxprodusta) + showK + iconStr + "</div>";
      } else if(_type == "astock"){
        pad01Arr +=
          ' <div class="code_txt">' + _name + iconStr + "</div>";
      } else{
        pad01Arr += ' <span class="code_txt">' + _name + showGdr + "</span>";
      }

      pad01Arr += "</div>";
      pad01Arr += '<table width="100%">';
      pad01Arr += " <tr>";

      if (
        _type == "index" ||
        _type == "astock" ||
        _type == "kcbstock"
      ) {
        pad01Arr +=
          '  <td rowspan="2"><div class="quotes_last ' +
          classes +
          '">' +
          _last +
          "</div></td>";
        pad01Arr +=
          '  <td align="right"><span class="quotes_rate ' +
          classes +
          '">' +
          (_change.toFixed(2) > 0 ?
            "+" + _change.toFixed(2) :
            _change.toFixed(2)) +
          "</span></td>";
        pad01Arr += " </tr>";
        pad01Arr += " <tr>";
        pad01Arr +=
          '  <td align="right"><span class="quotes_change ' +
          classes +
          '">' +
          _chgRate.toFixed(2) +
          "%</span></td>";
        pad01Arr += " </tr>";
        pad01Arr += "</table>";
        pad01Arr += "</li>";
      } else if (
        // 债券限制三位小数
        _type == "gbf" ||
        _type == "cpf" ||
        _type == "cbf" ||
        _type == "bond"
      ) {
        pad01Arr +=
          '  <td rowspan="2"><div class="quotes_last ' +
          classes +
          '">' +
          _last.toFixed(3) +
          "</div></td>";
        pad01Arr +=
          '  <td align="right"><span class="quotes_rate ' +
          classes +
          '">' +
          (_change.toFixed(3) > 0 ?
            "+" + _change.toFixed(3) :
            _change.toFixed(3)) +
          "</span></td>";
        pad01Arr += " </tr>";
        pad01Arr += " <tr>";
        pad01Arr +=
          '  <td align="right"><span class="quotes_change ' +
          classes +
          '">' +
          _chgRate.toFixed(2) +
          "%</span></td>";
        pad01Arr += " </tr>";
        pad01Arr += "</table>";
        pad01Arr += "</li>";
      } else if (_type == "huigou") {
        pad01Arr +=
          '  <td rowspan="2"><div class="quotes_last ' +
          classes +
          '">' +
          _last +
          "</div></td>";
        pad01Arr +=
          '  <td align="right"><div class="d-flex justify-content-between w-75"><span>涨跌值</span><span class="quotes_rate ' +
          classes +
          '">' +
          (_change.toFixed(3) > 0 ?
            "+" + _change.toFixed(3) :
            _change.toFixed(3)) +
          "</span></div></td>";
        pad01Arr += " </tr>";
        pad01Arr += " <tr>";
        pad01Arr +=
          '  <td align="right"><div class="d-flex justify-content-between w-75"><span>均价</span><span class="quotes_change hgjj ' +
          classes +
          '"></span></div></td>';
        pad01Arr += " </tr>";
        pad01Arr += "</table>";
        pad01Arr += "</li>";
      } else if (_type == "bstock") {
        pad01Arr +=
          '  <td rowspan="2"><div class="quotes_last ' +
          classes +
          '">' +
          _last +
          "</div></td>";
        pad01Arr +=
          '  <td align="right"><span class="quotes_rate ' +
          classes +
          '">' +
          (_change.toFixed(3) > 0 ?
            "+" + _change.toFixed(3) :
            _change.toFixed(3)) +
          "</span></td>";
        pad01Arr += " </tr>";
        pad01Arr += " <tr>";
        pad01Arr +=
          '  <td align="right"><span class="quotes_change ' +
          classes +
          '">' +
          _chgRate.toFixed(3) +
          "%</span></td>";
        pad01Arr += " </tr>";
        pad01Arr += "</table>";
        pad01Arr += "</li>";
      } else {
        pad01Arr +=
          '  <td rowspan="2"><div class="quotes_last ' +
          classes +
          '">' +
          _last +
          "</div></td>";
        pad01Arr +=
          '  <td align="right"><span class="quotes_rate ' +
          classes +
          '">' +
          (_change.toFixed(3) > 0 ?
            "+" + _change.toFixed(3) :
            _change.toFixed(3)) +
          "</span></td>";
        pad01Arr += " </tr>";
        pad01Arr += " <tr>";
        pad01Arr +=
          '  <td align="right"><span class="quotes_change ' +
          classes +
          '">' +
          _chgRate.toFixed(2) +
          "%</span></td>";
        pad01Arr += " </tr>";
        pad01Arr += "</table>";
        pad01Arr += "</li>";
      }

      /* 卖五 */
      pad02Arr += '<li class="d-flex py-2 flex-column">';
      pad02Arr += '<div class="quotes_Sell">';
      pad02Arr += '<table style="width:100%;">';

      if (_type == "gbf" || _type == "cpf" || _type == "cbf" || _type == "bond") {
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖五</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[8]) +
          '">' +
          _ask[8].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[9] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖四</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[6]) +
          '">' +
          _ask[6].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[7] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖三</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[4]) +
          '">' +
          _ask[4].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[5] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖二</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[2]) +
          '">' +
          _ask[2].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[3] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖一</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[0]) +
          '">' +
          _ask[0].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[1] + "</td>";
        pad02Arr += " </tr>";
      } else if (_type == "huigou") {
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖五</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[8]) +
          '">' +
          _ask[8].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[9] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖四</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[6]) +
          '">' +
          _ask[6].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[7] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖三</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[4]) +
          '">' +
          _ask[4].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[5] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖二</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[2]) +
          '">' +
          _ask[2].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[3] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖一</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[0]) +
          '">' +
          _ask[0].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _ask[1] + "</td>";
        pad02Arr += " </tr>";
        // 除债券
      } else if (
        _type == "index" ||
        _type == "astock" ||
        _type == "kcbstock"
      ) {
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖五</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[8]) +
          '">' +
          _ask[8].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[9] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖四</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[6]) +
          '">' +
          _ask[6].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[7] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖三</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[4]) +
          '">' +
          _ask[4].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[5] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖二</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[2]) +
          '">' +
          _ask[2].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[3] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖一</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[0]) +
          '">' +
          _ask[0].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[1] / 100) +
          "</td>";
        pad02Arr += " </tr>";
      } else {
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖五</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[8]) +
          '">' +
          _ask[8].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[9] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖四</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[6]) +
          '">' +
          _ask[6].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[7] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖三</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[4]) +
          '">' +
          _ask[4].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[5] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖二</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[2]) +
          '">' +
          _ask[2].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[3] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>卖一</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_ask[0]) +
          '">' +
          _ask[0].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_ask[1] / 100) +
          "</td>";
        pad02Arr += " </tr>";
      }

      pad02Arr += "</table>";
      pad02Arr += "</div>";

      /* 买五 */
      pad02Arr += '<div class="quotes_buy">';
      pad02Arr += '<table style="width:100%;">';

      if (_type == "gbf" || _type == "cpf" || _type == "cbf" || _type == "bond") {
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买一</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[0]) +
          '">' +
          _bid[0].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[1] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买二</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[2]) +
          '">' +
          _bid[2].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[3] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买三</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[4]) +
          '">' +
          _bid[4].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[5] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买四</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[6]) +
          '">' +
          _bid[6].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[7] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买五</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[8]) +
          '">' +
          _bid[8].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[9] + "</td>";
        pad02Arr += " </tr>";
      } else if (_type == "huigou") {
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买一</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[0]) +
          '">' +
          _bid[0].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[1] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买二</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[2]) +
          '">' +
          _bid[2].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[3] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买三</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[4]) +
          '">' +
          _bid[4].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[5] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买四</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[6]) +
          '">' +
          _bid[6].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[7] + "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买五</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[8]) +
          '">' +
          _bid[8].toFixed(3) +
          "</span></td>";
        pad02Arr += '  <td class="text-right digital_num">' + _bid[9] + "</td>";
        pad02Arr += " </tr>";
        // 除债券
      } else if (
        _type == "index" ||
        _type == "astock" ||
        _type == "kcbstock"
      ) {
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买一</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[0]) +
          '">' +
          _bid[0].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[1] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买二</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[2]) +
          '">' +
          _bid[2].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[3] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买三</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[4]) +
          '">' +
          _bid[4].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[5] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买四</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[6]) +
          '">' +
          _bid[6].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[7] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买五</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[8]) +
          '">' +
          _bid[8].toFixed(2) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[9] / 100) +
          "</td>";
        pad02Arr += " </tr>";
      } else {
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买一</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[0]) +
          '">' +
          _bid[0].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[1] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买二</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[2]) +
          '">' +
          _bid[2].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[3] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买三</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[4]) +
          '">' +
          _bid[4].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[5] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买四</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[6]) +
          '">' +
          _bid[6].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[7] / 100) +
          "</td>";
        pad02Arr += " </tr>";
        pad02Arr += " <tr>";
        pad02Arr += "  <td>买五</td>";
        pad02Arr +=
          '  <td class="text-center"><span class="' +
          zhangdie(_bid[8]) +
          '">' +
          _bid[8].toFixed(3) +
          "</span></td>";
        pad02Arr +=
          '  <td class="text-right digital_num">' +
          Math.round(_bid[9] / 100) +
          "</td>";
        pad02Arr += " </tr>";
      }

      pad02Arr += "</table>";
      pad02Arr += "</div>";
      pad02Arr += "</li>";

      /* 产品行情 */
      if (_type == "index" || _type == "astock" || _type == "kcbstock") {
        pad03Arr += '<li class="d-flex flex-column">';
        pad03Arr += ' <div class="quotes_close">';
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>昨收</span>";
        pad03Arr += '   <span class="digital_num">' + _prevClose + "</span>";
        pad03Arr += "  </div>";
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>开盘</span>";
        pad03Arr +=
          '   <span class="digital_num ' +
          zhangdie(_open) +
          '">' +
          _open +
          "</span>";
        pad03Arr += "  </div>";
      } else if (_type == "gbf" || _type == "cpf" || _type == "cbf" || _type == "bond") {
        pad03Arr += '<li class="d-flex flex-column">';
        pad03Arr += ' <div class="quotes_close">';
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>昨收</span>";
        pad03Arr +=
          '   <span class="digital_num">' +
          parseFloat(_prevClose).toFixed(3) +
          "</span>";
        pad03Arr += "  </div>";
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>开盘</span>";
        pad03Arr +=
          '   <span class="digital_num ' +
          zhangdie(_open) +
          '">' +
          parseFloat(_open).toFixed(3) +
          "</span>";
        pad03Arr += "  </div>";
      } else {
        pad03Arr += '<li class="d-flex flex-column">';
        pad03Arr += ' <div class="quotes_close">';
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>昨收</span>";
        pad03Arr += '   <span class="digital_num">' + _prevClose + "</span>";
        pad03Arr += "  </div>";
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>开盘</span>";
        pad03Arr +=
          '   <span class="digital_num ' +
          zhangdie(_open) +
          '">' +
          _open +
          "</span>";
        pad03Arr += "  </div>";
      }

      if (_type == "index" || _type == "astock" || _type == "kcbstock") {
        pad03Arr += " </div>";
        pad03Arr += ' <div class="quotes_new">';
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>最高</span>";
        pad03Arr +=
          '   <span class="digital_num ' +
          zhangdie(_high) +
          '">' +
          _high +
          "</span>";
        pad03Arr += "  </div>";
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>最低</span>";
        pad03Arr +=
          '   <span class="digital_num ' +
          zhangdie(_low) +
          '">' +
          _low +
          "</span>";
        pad03Arr += "  </div>";
        // 债券债最高最低调整为三位
      } else if (_type == "gbf" || _type == "cpf" || _type == "cbf" || _type == "bond") {
        pad03Arr += " </div>";
        pad03Arr += ' <div class="quotes_new">';
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>最高</span>";
        pad03Arr +=
          '   <span class="digital_num ' +
          zhangdie(_high) +
          '">' +
          parseFloat(_high).toFixed(3) +
          "</span>";
        pad03Arr += "  </div>";
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>最低</span>";
        pad03Arr +=
          '   <span class="digital_num ' +
          zhangdie(_low) +
          '">' +
          parseFloat(_low).toFixed(3) +
          "</span>";
        pad03Arr += "  </div>";
      } else {
        pad03Arr += " </div>";
        pad03Arr += ' <div class="quotes_new">';
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>最高</span>";
        pad03Arr +=
          '   <span class="digital_num ' +
          zhangdie(_high) +
          '">' +
          _high +
          "</span>";
        pad03Arr += "  </div>";
        pad03Arr += '  <div class="digital_con">';
        pad03Arr += "   <span>最低</span>";
        pad03Arr +=
          '   <span class="digital_num ' +
          zhangdie(_low) +
          '">' +
          _low +
          "</span>";
        pad03Arr += "  </div>";
      }

      pad03Arr += " </div>";
      pad03Arr += "</li>";

      /* 产品行情 */
      pad04Arr += "<li>";

      if (_type == "index") {
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>成交量</span>";
        pad04Arr +=
          '  <span class="digital_num">' +
          (_volume / 10000).toFixed(0) +
          "万手</span>";
        pad04Arr += " </div>";
      } else if (["astock", "bstock", "kcbstock", "etf", "lof", "fund", "reits"].includes(_type)) {
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>成交量</span>";
        pad04Arr +=
          '  <span class="digital_num">' +
          (_volume / 100).toFixed(0) +
          "手</span>";
        pad04Arr += " </div>";
        // 债券
      } else if (["gbf", "cpf", "cbf", "bond", "huigou"].includes(_type)) {
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>成交量</span>";
        pad04Arr +=
          '  <span class="digital_num">' + _volume.toFixed(0) + "手</span>";
        pad04Arr += " </div>";
      }

      if (_type == "bstock") {
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>成交额</span>";
        pad04Arr +=
          '  <span class="digital_num">' +
          (_amount / 10000).toFixed(0) +
          "万美元</span>";
        pad04Arr += " </div>";
      } else if (_type == "huigou") {
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>成交额</span>";
        pad04Arr +=
          '  <span class="digital_num">' +
          (_amount / 10000).toFixed(0) +
          "万元</span>";
        pad04Arr += " </div>";
      } else {
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>成交额</span>";
        if (_amount >= 10000000000) {
          pad04Arr +=
            '  <span class="digital_num">' +
            (_amount / 100000000).toFixed(2) +
            "亿元</span>";
        } else {
          pad04Arr +=
            '  <span class="digital_num">' +
            (_amount / 10000).toFixed(0) +
            "万元</span>";
        }
        pad04Arr += " </div>";
      }

      if (_type === "astock" || _type === "kcbstock" || _type === "etf") {
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>盘后成交量</span>";
        pad04Arr +=
          '  <span class="digital_num">' +
          (_fpVolume / 100).toFixed(0) +
          "手</span>";
        pad04Arr += " </div>";
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>盘后成交额</span>";
        pad04Arr +=
          '  <span class="digital_num">' +
          (_fpAmount / 10000).toFixed(0) +
          "万元</span>";
        pad04Arr += " </div>";
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>盘后交易状态</span>";
        pad04Arr += '  <span class="digital_num">' + _fpPhaseStatus + "</span>";
        pad04Arr += " </div>";
      }

      pad04Arr += ' <div class="digital_con">';
      pad04Arr += "  <span>时间</span>";
      pad04Arr +=
        '  <span class="digital_num">' + _dDate + " " + _dTime + "</span>";
      pad04Arr += " </div>";

      if (["astock", "bstock", "kcbstock", "etf", "lof", "fund", "gbf", "cpf", "cbf", "bond", "huigou", "reits"].includes(_type)) {
        pad04Arr += ' <div class="digital_con">';
        pad04Arr += "  <span>交易状态</span>";
        pad04Arr +=
          '  <span class="digital_num">' + checkStatus(_tradephase) + "</span>";
        pad04Arr += " </div>";
      }

      pad04Arr += showGdrprevpx + showGdrratio;
      pad04Arr += "</li>";

      $(".quotes_dataCon ul").html(pad01Arr + pad02Arr + pad03Arr + pad04Arr);

      if (_lineType == 0) {
        if (resultData.snap.length < 1) {
          $("#market_ticker").html(
            '<div class="d-flex align-items-center justify-content-center noChart_message">暂无走势信息</div>'
          );
        }
        if (_tradephase.replace(/\s/gi, "") == "P1") {
          $("#market_ticker").html(
            '<div class="d-flex align-items-center justify-content-center noChart_message">停牌中</div>'
          );
        } else if (_tradephase.replace(/\s/gi, "") == "C1") {
          $("#market_ticker").html(
            '<div class="d-flex align-items-center justify-content-center noChart_message">集合竞价中</div>'
          );
        } else {
          if (_type != "huigou") {
            drawKTimeChart(
              _code,
              _type,
              "market_kchart",
              "market_ticker",
              _isFirst,
              isBond
            );
            drawOneDayChart(
              _code,
              "market_ticker",
              "",
              _isFirst,
              _type,
              isBond
            );
          } else {
            drawKTimeChart(
              _code,
              _type,
              "market_kchart",
              "market_ticker",
              _isFirst,
              isBond
            );
            drawOneDayHGChart(_code, "market_ticker", "", _isFirst, isBond);
          }
        }
      } else {
        drawKChart(_code, "market_ticker", _isFirst, isBond);
      }
    },
  });
}